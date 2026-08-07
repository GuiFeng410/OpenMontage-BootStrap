"""Agnes multimodal product-image understanding for public HTTPS image URLs."""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.parse import urlparse

from tools._agnes import AGNES_BASE, get_agnes_api_key
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

_DEFAULT_MODEL = "agnes-2.5-flash"
_ALLOWED_MODELS = {"agnes-2.0-flash", "agnes-2.5-flash"}

_SYSTEM_PROMPT = """你是商品素材分析助手。只根据图片中可见内容输出 JSON，不要编造商品规格、
品牌、材质或人物身份。输出对象必须含 images 数组；每项含 url、suggested_class（product_hero /
product_detail / product_angle / on_body / unknown）、description_zh、confidence（0 到 1）和
risks_zh（字符串数组）。"""


class AgnesVision(BaseTool):
    """Classify public product images with an Agnes multimodal chat model."""

    name = "agnes_vision"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "image_understanding"
    provider = "agnes"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API
    dependencies = ["env:AGNES_API_KEY"]
    install_instructions = (
        "Set AGNES_API_KEY (or AGNES_AI_API_KEY) to an Agnes AI API key. "
        "This tool accepts public HTTPS image URLs only."
    )
    capabilities = ["classify_product_image", "extract_visible_product_features"]
    supports = {"public_https_url": True, "local_path": False, "data_uri": False}
    best_for = ["classifying product reference images before planning"]
    not_good_for = ["local files before controlled upload is configured"]
    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=10, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["image_urls", "model"]
    side_effects = ["calls Agnes multimodal API with public image URLs"]
    user_visible_verification = ["Confirm the suggested image classifications"]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if get_agnes_api_key() else ToolStatus.UNAVAILABLE

    @staticmethod
    def _validate_urls(values: Any) -> list[str]:
        if not isinstance(values, list) or not values:
            raise ValueError("image_urls must contain at least one public HTTPS image URL")
        urls = [str(value).strip() for value in values]
        if any(
            not url
            or urlparse(url).scheme != "https"
            or not urlparse(url).netloc
            for url in urls
        ):
            raise ValueError("image_urls only accepts public https URLs")
        return urls

    def build_payload(self, inputs: dict[str, Any]) -> dict[str, Any]:
        image_urls = self._validate_urls(inputs.get("image_urls"))
        model = str(inputs.get("model") or os.environ.get("AGNES_VISION_MODEL") or _DEFAULT_MODEL)
        if model not in _ALLOWED_MODELS:
            raise ValueError(f"Unsupported Agnes vision model: {model}")
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": "请分析以下商品图片，并严格按系统要求返回 JSON。",
            }
        ]
        content.extend(
            {"type": "image_url", "image_url": {"url": url}} for url in image_urls
        )
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "temperature": 0,
        }

    @staticmethod
    def _parse_content(data: dict[str, Any]) -> dict[str, Any]:
        choices = data.get("choices") or []
        message = choices[0].get("message") if choices else {}
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ValueError("Agnes vision response is missing message content")
        clean = content.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(clean)
        if not isinstance(result, dict) or not isinstance(result.get("images"), list):
            raise ValueError("Agnes vision response must be a JSON object with images")
        return result

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = get_agnes_api_key()
        if not api_key:
            return ToolResult(success=False, error="AGNES_API_KEY not set. " + self.install_instructions)

        start = time.time()
        try:
            import requests

            payload = self.build_payload(inputs)
            response = requests.post(
                f"{AGNES_BASE}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            result = self._parse_content(response.json())
        except Exception as exc:
            return ToolResult(success=False, error=f"Agnes vision analysis failed: {exc}")

        return ToolResult(
            success=True,
            data=result,
            duration_seconds=round(time.time() - start, 2),
            model=payload["model"],
        )
