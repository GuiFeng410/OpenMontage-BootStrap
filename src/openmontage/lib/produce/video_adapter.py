"""Paid video generate adapters. Does not switch providers."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from lib.produce.job_store import (
    ProduceJobError,
    _projects_root,
)

GENERATE_RETRY_LIMIT = 5
GENERATE_RETRY_BASE_SECONDS = 20

RETRY_EXHAUSTED_ZH = (
    "同一渠道同一模型已重试 5 次仍失败。项目已冻结。"
    "可回库页继续这个项目，或换模型另开。不会自动换渠道。"
)

_RATE_LIMIT_MARKERS = (
    "503",
    "502",
    "429",
    "Unavailable",
    "10053",
    "10054",
    "Connection aborted",
    "ConnectionReset",
    "ConnectionError",
)

_PAID_PROVIDERS = (
    "agnes",
    "kling",
    "seedance",
    "sora",
    "veo",
    "minimax",
    "runway",
    "tokenhub",
    "pixverse",
)

_HEAVY_KEY_HINTS = {
    "agnes": ("AGNES_API_KEY", "AGNES_AI_API_KEY"),
    "kling": ("KLING_API_KEY",),
    "seedance": ("FAL_KEY", "FAL_AI_API_KEY"),
    "sora": ("OPENAI_API_KEY",),
    "veo": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "FAL_KEY", "FAL_AI_API_KEY"),
    "minimax": ("FAL_KEY", "FAL_AI_API_KEY"),
    "runway": ("RUNWAY_API_KEY", "RUNWAYML_API_SECRET"),
    "tokenhub": ("TOKENHUB_API_KEY", "TENCENT_TOKENHUB_API_KEY"),
    "pixverse": ("PIXVERSE_API_KEY", "TOKENHUB_API_KEY", "TENCENT_TOKENHUB_API_KEY"),
}

def _kling_duration(seconds: float) -> str:
    value = int(round(float(seconds) or 5))
    return str(min(15, max(3, value)))

def _video_extras(
    provider: str,
    still_path: str,
    duration: float,
    aspect: str,
) -> dict[str, Any]:
    if provider == "agnes":
        return {
            "operation": "image_to_video",
            "duration": duration,
            "aspect_ratio": aspect,
            "image_path": still_path,
        }
    if provider == "kling":
        return {
            "operation": "image_to_video",
            "duration": _kling_duration(duration),
            "reference_image_path": still_path,
        }
    payload = {
        "operation": "image_to_video",
        "duration": duration,
        "aspect_ratio": aspect,
        "image_path": still_path,
        "reference_image_path": still_path,
    }
    if provider in {"tokenhub", "pixverse"}:
        try:
            payload["duration"] = int(round(float(duration) or 5))
        except (TypeError, ValueError):
            payload["duration"] = 5
    return payload

def _retry_backoff_seconds(attempt: int, error: str) -> float:
    """Backoff before next attempt; longer when Agnes rate-limits / drops the socket."""
    base = float(GENERATE_RETRY_BASE_SECONDS)
    text = error or ""
    if any(marker in text for marker in _RATE_LIMIT_MARKERS):
        return base * (2 ** max(0, attempt - 1))
    return max(3.0, base / 2)


def call_video_generate_with_retries(
    generate: Callable[..., Any],
    *args: Any,
    dest: Path | None = None,
) -> Any:
    """Retry the same provider/model up to GENERATE_RETRY_LIMIT times."""
    last_error = "分段生成失败，未换渠道。"
    last_result: Any = None
    for attempt in range(1, GENERATE_RETRY_LIMIT + 1):
        try:
            last_result = generate(*args)
        except Exception as exc:
            last_error = str(exc) or last_error
            if attempt >= GENERATE_RETRY_LIMIT:
                raise ProduceJobError(
                    f"{RETRY_EXHAUSTED_ZH} 最后错误：{last_error}",
                    code="video_generate_failed",
                    extra={
                        "retry_exhausted": True,
                        "generate_attempts": attempt,
                    },
                ) from exc
            time.sleep(_retry_backoff_seconds(attempt, last_error))
            continue
        failed = isinstance(last_result, dict) and last_result.get("success") is False
        missing = dest is not None and (
            not dest.is_file() or dest.stat().st_size <= 0
        )
        if failed:
            last_error = str(
                (last_result or {}).get("error") if isinstance(last_result, dict) else last_error
            ) or last_error
        if failed or missing:
            if attempt >= GENERATE_RETRY_LIMIT:
                raise ProduceJobError(
                    f"{RETRY_EXHAUSTED_ZH} 最后错误：{last_error}",
                    code="video_generate_failed",
                    extra={
                        "retry_exhausted": True,
                        "generate_attempts": attempt,
                    },
                )
            time.sleep(_retry_backoff_seconds(attempt, last_error))
            continue
        return last_result
    raise ProduceJobError(
        RETRY_EXHAUSTED_ZH,
        code="video_generate_failed",
        extra={"retry_exhausted": True, "generate_attempts": GENERATE_RETRY_LIMIT},
    )

def _board_tokenhub_generate(
    provider: str,
    prompt: str,
    output_path: str,
    extras_json: str = "{}",
    confirm: bool = False,
    confirm_sample_ok: bool = False,
) -> dict[str, Any]:
    if not confirm or not confirm_sample_ok:
        raise ProduceJobError("看板开烧需要用户已确认开始出片。", code="confirm_required")
    try:
        extras = json.loads(extras_json or "{}") if extras_json else {}
    except json.JSONDecodeError:
        extras = {}
    if not isinstance(extras, dict):
        extras = {}
    model = str(extras.get("model") or "").strip()
    if not model:
        model = "pixverse-video-v6.0" if provider == "pixverse" else "hy-video-1.5"
    dest = Path(output_path)
    if not dest.is_absolute():
        dest = _projects_root() / output_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    from tools._tokenhub.video import generate_video

    duration_raw = extras.get("duration")
    try:
        duration = int(round(float(duration_raw))) if duration_raw is not None else 5
    except (TypeError, ValueError):
        duration = 5
    image_path = extras.get("image_path") or extras.get("reference_image_path")
    result = generate_video(
        prompt,
        model=model,
        image_path=str(image_path) if image_path else None,
        output_path=dest,
        duration=duration,
        aspect_ratio=str(extras.get("aspect_ratio") or "16:9"),
        project_id=str(extras.get("project_id") or "").strip()
        or str(output_path).replace("\\", "/").split("/")[0],
        # 看板「开始出片」即用户对本项目本地图临时上传的明确授权；禁止静默换渠。
        user_authorized_upload=True,
    )
    return {
        "success": True,
        "output_path": str(result.get("output_path") or dest),
        **{
            key: result[key]
            for key in ("job_id", "model")
            if isinstance(result, dict) and key in result
        },
    }

def _resolve_video_generate(
    provider: str,
    video_generate: Callable[..., dict[str, Any]] | None,
) -> Callable[..., Any]:
    if video_generate is not None:
        return video_generate
    if provider in {"tokenhub", "pixverse"}:
        return _board_tokenhub_generate
    from openmontage.mcp.providers_video.tools import video_generate as generate

    return generate
