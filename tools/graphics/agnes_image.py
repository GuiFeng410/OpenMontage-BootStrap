"""Agnes AI image generation (text-to-image and image-to-image)."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tools._agnes import AGNES_BASE, get_agnes_api_key, normalize_image_ref
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

_DEFAULT_MODEL = "agnes-image-2.1-flash"
_ALLOWED_MODELS = ["agnes-image-2.1-flash", "agnes-image-2.0-flash"]
_COST_PER_IMAGE = 0.003  # Standard list price; promo may be $0 — see install_instructions


class AgnesImage(BaseTool):
    name = "agnes_image"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
    provider = "agnes"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []
    install_instructions = (
        "Set AGNES_API_KEY (or AGNES_AI_API_KEY) to your Agnes AI API key.\n"
        "  Get one at https://agnes-ai.com/ (console → API Key)\n"
        "  Docs: https://wiki.agnes-ai.com/en/docs/agnes-image-21-flash.md\n"
        "  Note: docs may show a temporary $0/image promo; estimates use standard $0.003/image."
    )
    agent_skills = ["flux-best-practices"]

    capabilities = [
        "generate_image",
        "edit_image",
        "text_to_image",
        "image_to_image",
    ]
    supports = {
        "text_to_image": True,
        "image_to_image": True,
        "image_edit": True,
        "aspect_ratio": True,
        "resolution": True,
        "reference_image": True,
        "multiple_reference_images": True,
    }
    best_for = [
        "budget-friendly text-to-image and image-to-image via Agnes Flash models",
        "high-information-density scenes with Agnes Image 2.1 Flash",
        "cost-efficient stills when AGNES_API_KEY is configured",
    ]
    not_good_for = ["offline generation", "projects without Agnes API access"]
    fallback_tools = ["flux_image", "dashscope_image", "openai_image", "grok_image"]
    quality_score = 0.85

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_image", "image_to_image", "generate", "edit"],
                "default": "text_to_image",
            },
            "generation_mode": {
                "type": "string",
                "enum": ["generate", "edit"],
                "description": "Alias for operation used by image_selector.",
            },
            "model": {
                "type": "string",
                "enum": _ALLOWED_MODELS,
                "default": _DEFAULT_MODEL,
            },
            "size": {
                "type": "string",
                "description": "Tier (1K/2K/3K/4K) or legacy WxH such as 1024x768.",
                "default": "1K",
            },
            "ratio": {
                "type": "string",
                "enum": ["1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9"],
                "default": "16:9",
            },
            "aspect_ratio": {
                "type": "string",
                "description": "Alias for ratio.",
            },
            "image_url": {"type": "string", "description": "Source image URL for image-to-image"},
            "image_path": {"type": "string", "description": "Local source image path for image-to-image"},
            "image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple source image URLs for multi-image composition",
            },
            "image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple local source image paths",
            },
            "return_base64": {
                "type": "boolean",
                "default": False,
                "description": "Request Base64 output for text-to-image (top-level return_base64).",
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["prompt", "model", "size", "ratio", "operation"]
    side_effects = ["writes image file to output_path", "calls Agnes images API"]
    user_visible_verification = ["Inspect generated image for relevance and quality"]

    def get_status(self) -> ToolStatus:
        if get_agnes_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return _COST_PER_IMAGE

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 45.0

    @staticmethod
    def _collect_input_images(inputs: dict[str, Any]) -> list[str]:
        images: list[str] = []
        primary = normalize_image_ref(inputs.get("image_url"), inputs.get("image_path"))
        if primary:
            images.append(primary)
        for url in inputs.get("image_urls") or []:
            images.append(str(url))
        for path in inputs.get("image_paths") or []:
            images.append(normalize_image_ref(None, path) or "")
        return [img for img in images if img]

    def _resolve_operation(self, inputs: dict[str, Any], input_images: list[str]) -> str:
        op = str(inputs.get("operation") or inputs.get("generation_mode") or "text_to_image")
        if op in {"edit", "image_to_image"} or input_images:
            return "image_to_image"
        return "text_to_image"

    def build_payload(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Build Agnes images/generations request body (public for tests)."""
        input_images = self._collect_input_images(inputs)
        operation = self._resolve_operation(inputs, input_images)
        model = str(inputs.get("model") or _DEFAULT_MODEL)
        if model not in _ALLOWED_MODELS:
            raise ValueError(f"Unsupported Agnes image model: {model}")

        ratio = inputs.get("ratio") or inputs.get("aspect_ratio") or "16:9"
        size = str(inputs.get("size") or "1K")
        payload: dict[str, Any] = {
            "model": model,
            "prompt": inputs["prompt"],
            "size": size,
            "ratio": ratio,
        }

        extra_body: dict[str, Any] = {"response_format": "url"}
        if operation == "image_to_image":
            if not input_images:
                raise ValueError(
                    "image_to_image requires image_url/image_path or image_urls/image_paths"
                )
            extra_body["image"] = input_images
            if inputs.get("return_base64"):
                extra_body["response_format"] = "b64_json"
        elif inputs.get("return_base64"):
            payload["return_base64"] = True
            extra_body.pop("response_format", None)

        if extra_body:
            payload["extra_body"] = extra_body
        return payload

    @staticmethod
    def _infer_extension(url: str | None) -> str:
        if not url:
            return ".png"
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            return suffix
        return ".png"

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = get_agnes_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="AGNES_API_KEY not set. " + self.install_instructions,
            )

        import requests

        start = time.time()
        try:
            payload = self.build_payload(inputs)
            response = requests.post(
                f"{AGNES_BASE}/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=360,
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("data") or []
            if not items:
                return ToolResult(success=False, error="Agnes returned no image outputs")

            item = items[0]
            extension = self._infer_extension(item.get("url"))
            output_path = Path(inputs.get("output_path") or f"agnes_image{extension}")
            if not output_path.suffix:
                output_path = output_path.with_suffix(extension)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if item.get("b64_json"):
                output_path.write_bytes(base64.b64decode(item["b64_json"]))
            else:
                image_url = item.get("url")
                if not image_url:
                    return ToolResult(success=False, error="Agnes image output missing url")
                download = requests.get(image_url, timeout=120)
                download.raise_for_status()
                output_path.write_bytes(download.content)

        except Exception as e:
            return ToolResult(success=False, error=f"Agnes image generation failed: {e}")

        return ToolResult(
            success=True,
            data={
                "provider": "agnes",
                "model": payload["model"],
                "prompt": inputs["prompt"],
                "operation": self._resolve_operation(inputs, self._collect_input_images(inputs)),
                "output": str(output_path),
                "output_path": str(output_path),
                "size": payload.get("size"),
                "ratio": payload.get("ratio"),
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=payload["model"],
        )
