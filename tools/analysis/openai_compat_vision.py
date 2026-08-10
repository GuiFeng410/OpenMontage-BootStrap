"""OpenAI-compatible vision (local images → text) for commercial asset gate.

Env (1C):
  VISION_API_KEY or DASHSCOPE_API_KEY
  VISION_BASE_URL (default DashScope compatible-mode)
  VISION_MODEL (default qwen-vl-max)
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

_DEFAULT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "qwen-vl-max"
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

_SYSTEM_PROMPT = """你是商品素材分析助手。只根据图片中可见内容输出 JSON，不要编造规格、品牌或人物身份。
输出对象必须含 images 数组；每项含 file（若已知）、suggested_class（product_hero /
product_detail / product_angle / on_body / packaging / lifestyle / unknown）、
description_zh、usable_for_zh（可用于哪些镜头）、confidence（0 到 1）和 risks_zh（字符串数组）。"""


def resolve_vision_env() -> dict[str, Any]:
    """Resolve OpenAI-compatible vision credentials from environment."""
    api_key = (
        (os.environ.get("VISION_API_KEY") or "").strip()
        or (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
    )
    base_url = (os.environ.get("VISION_BASE_URL") or _DEFAULT_BASE).strip().rstrip("/")
    model = (os.environ.get("VISION_MODEL") or _DEFAULT_MODEL).strip()
    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "available": bool(api_key),
        "key_source": (
            "VISION_API_KEY"
            if (os.environ.get("VISION_API_KEY") or "").strip()
            else ("DASHSCOPE_API_KEY" if api_key else "")
        ),
    }


def _data_uri(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if not mime or not mime.startswith("image/"):
        ext = path.suffix.lower().lstrip(".")
        mime = f"image/{'jpeg' if ext in {'jpg', 'jpeg'} else ext or 'jpeg'}"
    raw = path.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _parse_json_content(content: str) -> dict[str, Any]:
    clean = (content or "").strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    result = json.loads(clean)
    if not isinstance(result, dict) or not isinstance(result.get("images"), list):
        raise ValueError("vision response must be a JSON object with images[]")
    return result


class OpenAICompatVision(BaseTool):
    """Describe / classify local product images via OpenAI-compatible VL API."""

    name = "openai_compat_vision"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "image_understanding"
    provider = "openai_compat"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API
    dependencies = ["env:VISION_API_KEY|DASHSCOPE_API_KEY"]
    install_instructions = (
        "Set DASHSCOPE_API_KEY (recommended) or VISION_API_KEY. "
        "Optional: VISION_BASE_URL, VISION_MODEL (default qwen-vl-max)."
    )
    capabilities = ["describe_product_image", "classify_product_image"]
    supports = {"public_https_url": True, "local_path": True, "data_uri": True}
    best_for = ["commercial asset gate when the chat model cannot see images"]
    not_good_for = ["replacing user confirmation of asset roles"]
    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=20, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["image_paths", "image_urls", "model"]
    side_effects = ["calls external vision API; may incur token cost"]
    user_visible_verification = ["Confirm suggested_class before writing asset_ledger"]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if resolve_vision_env()["available"] else ToolStatus.UNAVAILABLE

    def build_payload(self, inputs: dict[str, Any]) -> dict[str, Any]:
        cfg = resolve_vision_env()
        model = str(inputs.get("model") or cfg["model"] or _DEFAULT_MODEL)
        prompt = str(inputs.get("prompt") or "请分析这些商品图片，并严格按系统要求返回 JSON。")
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        file_labels: list[str] = []

        for raw in inputs.get("image_paths") or []:
            path = Path(str(raw)).expanduser().resolve()
            if path.suffix.lower() not in _ALLOWED_EXT:
                raise ValueError(f"unsupported image type: {path.name}")
            if not path.is_file():
                raise ValueError(f"image not found: {path}")
            content.append({"type": "image_url", "image_url": {"url": _data_uri(path)}})
            file_labels.append(path.name)

        for url in inputs.get("image_urls") or []:
            parsed = urlparse(str(url).strip())
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError("image_urls only accepts https URLs")
            content.append({"type": "image_url", "image_url": {"url": str(url).strip()}})
            file_labels.append(str(url).strip())

        if len(content) < 2:
            raise ValueError("provide at least one image_paths or image_urls entry")

        return {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "temperature": 0,
            "_file_labels": file_labels,
            "_base_url": str(inputs.get("base_url") or cfg["base_url"]),
            "_api_key": cfg["api_key"],
        }

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        cfg = resolve_vision_env()
        if not cfg["available"]:
            return ToolResult(
                success=False,
                error="VISION_API_KEY / DASHSCOPE_API_KEY not set. " + self.install_instructions,
            )

        start = time.time()
        model = str(inputs.get("model") or cfg["model"] or _DEFAULT_MODEL)
        try:
            import requests

            payload = self.build_payload(inputs)
            base_url = payload.pop("_base_url")
            api_key = payload.pop("_api_key")
            file_labels = payload.pop("_file_labels", [])
            model = str(payload.get("model") or model)
            response = requests.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            body = response.json()
            choices = body.get("choices") or []
            message = choices[0].get("message") if choices else {}
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            result = _parse_json_content(str(content or ""))
            images = result.get("images") or []
            for idx, row in enumerate(images):
                if isinstance(row, dict) and not row.get("file") and idx < len(file_labels):
                    row["file"] = file_labels[idx]
        except Exception as exc:
            return ToolResult(success=False, error=f"OpenAI-compat vision failed: {exc}")

        return ToolResult(
            success=True,
            data=result,
            duration_seconds=round(time.time() - start, 2),
            model=model,
        )
