"""Agnes AI video generation (async text-to-video and image-to-video)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

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

_MODEL = "agnes-video-v2.0"
_COST_PER_SECOND = 0.005  # Standard list price; promo may be $0 — see install_instructions
_DEFAULT_FRAME_RATE = 24
_DEFAULT_NUM_FRAMES = 121  # ~5s at 24fps; must be 8n+1


def duration_to_num_frames(duration_seconds: float, frame_rate: int = _DEFAULT_FRAME_RATE) -> int:
    """Map target duration to Agnes num_frames (8n+1, max 441)."""
    raw = int(round(float(duration_seconds) * int(frame_rate)))
    # Nearest 8n+1 at or below raw; if below 1, use 1.
    n = max(0, (raw - 1) // 8)
    frames = 8 * n + 1
    if frames < 1:
        frames = 1
    if frames > 441:
        frames = 441
    # If rounding down undershot a lot, try stepping up one notch when still within max.
    if frames + 8 <= 441 and abs((frames + 8) - raw) < abs(frames - raw):
        frames = frames + 8
    return frames


def validate_num_frames(num_frames: int) -> int:
    """Ensure num_frames follows Agnes 8n+1 rule and is within [1, 441]."""
    value = int(num_frames)
    if value < 1:
        raise ValueError("num_frames must be >= 1")
    if value > 441:
        raise ValueError("num_frames must be <= 441")
    if (value - 1) % 8 != 0:
        raise ValueError(f"num_frames must follow 8n+1 rule, got {value}")
    return value


class AgnesVideo(BaseTool):
    name = "agnes_video"
    version = "0.1.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "agnes"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = []
    install_instructions = (
        "Set AGNES_API_KEY (or AGNES_AI_API_KEY) to your Agnes AI API key.\n"
        "  Get one at https://agnes-ai.com/ (console → API Key)\n"
        "  Docs: https://wiki.agnes-ai.com/en/docs/agnes-video-v20.md\n"
        "  Note: docs may show a temporary $0/second promo; estimates use standard $0.005/second."
    )
    agent_skills = ["ai-video-gen"]

    capabilities = ["text_to_video", "image_to_video"]
    supports = {
        "text_to_video": True,
        "image_to_video": True,
        "camera_direction": True,
        "short_clips": True,
        "cinematic_quality": True,
    }
    best_for = [
        "budget-friendly text-to-video and image-to-video via Agnes Video V2.0",
        "short cinematic clips when AGNES_API_KEY is configured",
        "cost-efficient motion samples before committing to premium providers",
    ]
    not_good_for = ["offline generation", "projects without Agnes API access"]
    fallback_tools = ["seedance_video", "kling_video", "minimax_video", "veo_video"]
    quality_score = 0.8

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "operation": {
                "type": "string",
                "enum": ["text_to_video", "image_to_video"],
                "default": "text_to_video",
            },
            "model": {
                "type": "string",
                "enum": [_MODEL],
                "default": _MODEL,
            },
            "duration": {
                "type": ["number", "string"],
                "description": "Target duration in seconds; mapped to num_frames at frame_rate.",
                "default": 5,
            },
            "num_frames": {
                "type": "integer",
                "description": "Exact frame count (8n+1, <=441). Overrides duration when set.",
            },
            "frame_rate": {
                "type": "number",
                "minimum": 1,
                "maximum": 60,
                "default": _DEFAULT_FRAME_RATE,
            },
            "width": {"type": "integer", "default": 1152},
            "height": {"type": "integer", "default": 768},
            "aspect_ratio": {
                "type": "string",
                "enum": ["16:9", "9:16", "1:1", "4:3", "3:4"],
                "default": "16:9",
            },
            "negative_prompt": {"type": "string"},
            "seed": {"type": "integer"},
            "image_url": {"type": "string", "description": "Reference image URL for image_to_video"},
            "image_path": {"type": "string", "description": "Local reference image for image_to_video"},
            "reference_image_url": {"type": "string"},
            "reference_image_path": {"type": "string"},
            "mode": {
                "type": "string",
                "description": "Optional generation mode (e.g. ti2vid). Keyframes via extra_body reserved.",
            },
            "output_path": {"type": "string"},
            "poll_interval_seconds": {"type": "integer", "minimum": 2, "default": 5},
            "timeout_seconds": {"type": "integer", "minimum": 30, "default": 900},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["prompt", "operation", "num_frames", "frame_rate", "width", "height"]
    side_effects = ["writes video file to output_path", "calls Agnes videos API"]
    user_visible_verification = ["Watch generated clip for motion coherence and visual quality"]

    def get_status(self) -> ToolStatus:
        if get_agnes_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def _resolved_duration_seconds(self, inputs: dict[str, Any]) -> float:
        frame_rate = float(inputs.get("frame_rate") or _DEFAULT_FRAME_RATE)
        if inputs.get("num_frames") is not None:
            return validate_num_frames(int(inputs["num_frames"])) / frame_rate
        if inputs.get("duration") is not None:
            return float(inputs["duration"])
        return _DEFAULT_NUM_FRAMES / frame_rate

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return _COST_PER_SECOND * self._resolved_duration_seconds(inputs)

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return 90.0 + self._resolved_duration_seconds(inputs) * 10.0

    @staticmethod
    def _aspect_to_size(aspect_ratio: str | None) -> tuple[int, int]:
        mapping = {
            "16:9": (1152, 768),
            "9:16": (768, 1152),
            "1:1": (768, 768),
            "4:3": (1024, 768),
            "3:4": (768, 1024),
        }
        return mapping.get(aspect_ratio or "16:9", (1152, 768))

    def build_payload(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Build Agnes POST /v1/videos body (public for tests)."""
        operation = str(inputs.get("operation") or "text_to_video")
        frame_rate = int(inputs.get("frame_rate") or _DEFAULT_FRAME_RATE)
        if inputs.get("num_frames") is not None:
            num_frames = validate_num_frames(int(inputs["num_frames"]))
        elif inputs.get("duration") is not None:
            num_frames = duration_to_num_frames(float(inputs["duration"]), frame_rate)
        else:
            num_frames = _DEFAULT_NUM_FRAMES

        width = inputs.get("width")
        height = inputs.get("height")
        if width is None or height is None:
            width, height = self._aspect_to_size(inputs.get("aspect_ratio"))

        payload: dict[str, Any] = {
            "model": inputs.get("model") or _MODEL,
            "prompt": inputs["prompt"],
            "width": int(width),
            "height": int(height),
            "num_frames": num_frames,
            "frame_rate": frame_rate,
        }
        if inputs.get("negative_prompt"):
            payload["negative_prompt"] = inputs["negative_prompt"]
        if inputs.get("seed") is not None:
            payload["seed"] = int(inputs["seed"])
        if inputs.get("mode"):
            payload["mode"] = inputs["mode"]

        if operation == "image_to_video":
            image = normalize_image_ref(
                inputs.get("image_url") or inputs.get("reference_image_url"),
                inputs.get("image_path") or inputs.get("reference_image_path"),
            )
            if not image:
                raise ValueError(
                    "image_to_video requires image_url/image_path "
                    "(or reference_image_url/reference_image_path)"
                )
            payload["image"] = image

        return payload

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = get_agnes_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="AGNES_API_KEY not set. " + self.install_instructions,
            )

        import requests
        from tools.video._shared import probe_output

        start = time.time()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            payload = self.build_payload(inputs)
            create = requests.post(
                f"{AGNES_BASE}/v1/videos",
                headers=headers,
                json=payload,
                timeout=60,
            )
            create.raise_for_status()
            created = create.json()
            video_id = created.get("video_id") or created.get("id") or created.get("task_id")
            task_id = created.get("task_id") or created.get("id")
            if not video_id and not task_id:
                return ToolResult(success=False, error="Agnes create task returned no video_id/task_id")

            timeout_seconds = int(inputs.get("timeout_seconds", 900))
            poll_interval = int(inputs.get("poll_interval_seconds", 5))
            deadline = time.time() + timeout_seconds

            result_data: dict[str, Any] | None = None
            while time.time() < deadline:
                if video_id:
                    result = requests.get(
                        f"{AGNES_BASE}/agnesapi",
                        params={"video_id": video_id, "model_name": _MODEL},
                        headers={"Authorization": headers["Authorization"]},
                        timeout=30,
                    )
                else:
                    result = requests.get(
                        f"{AGNES_BASE}/v1/videos/{task_id}",
                        headers={"Authorization": headers["Authorization"]},
                        timeout=30,
                    )
                result.raise_for_status()
                result_data = result.json()
                status = str(result_data.get("status") or "").lower()
                # Live API uses pending -> in_progress -> completed (docs also list queued).
                if status == "completed":
                    break
                if status in {"failed", "error", "cancelled", "canceled"}:
                    detail = result_data.get("error") or result_data.get("message") or status
                    return ToolResult(success=False, error=f"Agnes video generation failed: {detail}")
                time.sleep(poll_interval)

            if not result_data or str(result_data.get("status") or "").lower() != "completed":
                return ToolResult(success=False, error="Agnes video generation timed out")

            metadata = result_data.get("metadata") if isinstance(result_data.get("metadata"), dict) else {}
            # Docs put the file under metadata.url; live responses expose top-level url.
            video_url = (
                result_data.get("url")
                or metadata.get("url")
                or result_data.get("video_url")
                or metadata.get("video_url")
            )
            if not video_url:
                return ToolResult(
                    success=False,
                    error="Agnes video output missing url (checked top-level and metadata.url)",
                )

            download = requests.get(video_url, timeout=300)
            download.raise_for_status()
            output_path = Path(inputs.get("output_path") or "agnes_video_output.mp4")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(download.content)

        except Exception as e:
            return ToolResult(success=False, error=f"Agnes video generation failed: {e}")

        probed = probe_output(output_path)
        return ToolResult(
            success=True,
            data={
                "provider": "agnes",
                "model": payload["model"],
                "prompt": inputs["prompt"],
                "operation": inputs.get("operation", "text_to_video"),
                "video_id": video_id,
                "task_id": task_id,
                "num_frames": payload["num_frames"],
                "frame_rate": payload["frame_rate"],
                "seconds": result_data.get("seconds") if result_data else None,
                "size": result_data.get("size") if result_data else None,
                "output": str(output_path),
                "output_path": str(output_path),
                "format": "mp4",
                **probed,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=payload["model"],
        )
