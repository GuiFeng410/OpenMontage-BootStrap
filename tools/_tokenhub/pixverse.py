"""TokenHub Pixverse video — T2V / I2V via /wand/pixverse/* (P0).

Reference / start-end modes are deferred (P2).
I2V requires a public http(s) image URL (img_id); local base64 is not wired yet.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal

from tools._tokenhub.client import (
    TokenHubClient,
    TokenHubError,
    get_tokenhub_api_key,
)
from tools._tokenhub.models import get_model
from tools._tokenhub.video import download_video

PIXVERSE_DEFAULT_MODEL = "pixverse-video-v6.0"
_DEFAULT_DURATION = 5
_DEFAULT_QUALITY = "720p"
_DEFAULT_ASPECT = "16:9"

_TERMINAL_OK = frozenset({"completed", "succeed", "success", "succeeded"})
_TERMINAL_FAIL = frozenset({"failed", "error", "cancelled", "canceled"})

PixverseMode = Literal["t2v", "i2v"]


def is_pixverse_model(model_id: str | None) -> bool:
    mid = (model_id or "").strip().lower()
    return mid.startswith("pixverse")


def _require_http_url(url: str, *, field: str = "img_id") -> str:
    value = str(url or "").strip()
    if not value.startswith(("http://", "https://")):
        raise TokenHubError(
            f"Pixverse I2V requires a public http(s) URL for {field} "
            f"(local paths / base64 not supported in P0). Got: {value[:80]!r}"
        )
    return value


def _extract_task_id(payload: dict[str, Any]) -> str:
    for key in ("task_id", "id", "job_id"):
        raw = payload.get(key)
        if raw:
            return str(raw)
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("task_id", "id", "job_id"):
            raw = data.get(key)
            if raw:
                return str(raw)
    return ""


def _extract_status(payload: dict[str, Any]) -> str:
    for key in ("status", "state", "task_status"):
        raw = payload.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip().lower()
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("status", "state", "task_status"):
            raw = data.get(key)
            if raw is not None and str(raw).strip():
                return str(raw).strip().lower()
    return ""


def _extract_video_url(payload: dict[str, Any]) -> str:
    candidates: list[Any] = [
        payload.get("video_url"),
        payload.get("url"),
        payload.get("output_url"),
    ]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend(
            [
                data.get("video_url"),
                data.get("url"),
                data.get("output_url"),
                data.get("video"),
            ]
        )
        output = data.get("output")
        if isinstance(output, dict):
            candidates.extend([output.get("video_url"), output.get("url")])
        elif isinstance(output, str):
            candidates.append(output)
    result = payload.get("result")
    if isinstance(result, dict):
        candidates.extend([result.get("video_url"), result.get("url")])

    for raw in candidates:
        if isinstance(raw, str) and raw.startswith(("http://", "https://")):
            return raw
        if isinstance(raw, list) and raw:
            first = raw[0]
            if isinstance(first, str) and first.startswith(("http://", "https://")):
                return first
            if isinstance(first, dict):
                for key in ("url", "video_url"):
                    nested = first.get(key)
                    if isinstance(nested, str) and nested.startswith(("http://", "https://")):
                        return nested
    return ""


def _error_message(payload: dict[str, Any]) -> str:
    for key in ("message", "msg", "error", "fail_reason"):
        raw = payload.get(key)
        if isinstance(raw, dict):
            nested = raw.get("message") or raw.get("msg") or raw.get("error")
            if nested:
                return str(nested)
        elif raw:
            return str(raw)
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("message", "msg", "error", "fail_reason"):
            raw = data.get(key)
            if raw:
                return str(raw)
    return ""


def submit_text_to_video(
    prompt: str,
    *,
    model: str = PIXVERSE_DEFAULT_MODEL,
    duration: int = _DEFAULT_DURATION,
    quality: str = _DEFAULT_QUALITY,
    aspect_ratio: str = _DEFAULT_ASPECT,
    client: TokenHubClient | None = None,
) -> dict[str, Any]:
    """POST /wand/pixverse/text-to-video."""
    known = get_model(model)
    if known is not None and known.status == "planned":
        raise TokenHubError(f"Pixverse model {model!r} is planned (not wired).")

    payload = {
        "model": model,
        "prompt": prompt,
        "duration": int(duration),
        "quality": quality,
        "aspect_ratio": aspect_ratio,
    }
    api = client or TokenHubClient()
    return api.post("/wand/pixverse/text-to-video", payload)


def submit_image_to_video(
    prompt: str,
    *,
    image_url: str,
    model: str = PIXVERSE_DEFAULT_MODEL,
    duration: int = _DEFAULT_DURATION,
    quality: str = _DEFAULT_QUALITY,
    client: TokenHubClient | None = None,
) -> dict[str, Any]:
    """POST /wand/pixverse/image-to-video. image_url → img_id (public URL only)."""
    known = get_model(model)
    if known is not None and known.status == "planned":
        raise TokenHubError(f"Pixverse model {model!r} is planned (not wired).")

    img_id = _require_http_url(image_url)
    payload = {
        "model": model,
        "prompt": prompt,
        "img_id": img_id,
        "duration": int(duration),
        "quality": quality,
    }
    api = client or TokenHubClient()
    return api.post("/wand/pixverse/image-to-video", payload)


def query_pixverse_task(
    task_id: str,
    *,
    client: TokenHubClient | None = None,
) -> dict[str, Any]:
    """GET /wand/pixverse/tasks/{task_id}."""
    tid = str(task_id or "").strip()
    if not tid:
        raise TokenHubError("Pixverse task_id is required")
    api = client or TokenHubClient()
    return api.get(f"/wand/pixverse/tasks/{tid}")


def poll_pixverse_task(
    task_id: str,
    *,
    poll_interval_seconds: float = 8.0,
    timeout_seconds: float = 900.0,
    client: TokenHubClient | None = None,
) -> dict[str, Any]:
    """Poll until completed or failed. Returns final query payload."""
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while True:
        last = query_pixverse_task(task_id, client=client)
        status = _extract_status(last)
        video_url = _extract_video_url(last)
        print(
            f"pixverse poll id={task_id} status={status or '?'}",
            flush=True,
        )
        if status in _TERMINAL_FAIL:
            raise TokenHubError(
                f"Pixverse task {task_id} ended with status={status}: {_error_message(last)}",
                response=last,
            )
        if status in _TERMINAL_OK or video_url:
            return last
        if time.monotonic() >= deadline:
            raise TokenHubError(
                f"Pixverse task {task_id} timed out after {timeout_seconds:.0f}s",
                response=last,
            )
        time.sleep(poll_interval_seconds)


def generate_pixverse_video(
    prompt: str,
    *,
    mode: PixverseMode = "t2v",
    model: str = PIXVERSE_DEFAULT_MODEL,
    image_url: str | None = None,
    image_path: str | None = None,
    output_path: str | Path | None = None,
    duration: int = _DEFAULT_DURATION,
    quality: str = _DEFAULT_QUALITY,
    aspect_ratio: str = _DEFAULT_ASPECT,
    poll_interval_seconds: float = 8.0,
    timeout_seconds: float = 900.0,
    client: TokenHubClient | None = None,
) -> dict[str, Any]:
    """Submit Pixverse T2V/I2V, poll, optionally download."""
    if not get_tokenhub_api_key() and (client is None or not client.api_key):
        raise TokenHubError("TOKENHUB_API_KEY is not set", http_status=401)

    if image_path and not image_url:
        raise TokenHubError(
            "Pixverse I2V does not accept local image_path in P0; "
            "pass a public http(s) image_url (maps to img_id)."
        )

    if mode == "i2v":
        if not image_url:
            raise TokenHubError("Pixverse I2V requires image_url (public http(s) URL)")
        submit = submit_image_to_video(
            prompt,
            image_url=image_url,
            model=model,
            duration=duration,
            quality=quality,
            client=client,
        )
    else:
        submit = submit_text_to_video(
            prompt,
            model=model,
            duration=duration,
            quality=quality,
            aspect_ratio=aspect_ratio,
            client=client,
        )

    task_id = _extract_task_id(submit)
    status = _extract_status(submit)
    if status in _TERMINAL_FAIL or not task_id:
        raise TokenHubError(
            f"Pixverse submit failed: {_error_message(submit) or submit}",
            response=submit,
        )

    # Some gateways return the video immediately on submit.
    video_url = _extract_video_url(submit)
    final = submit
    if not video_url:
        final = poll_pixverse_task(
            task_id,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
            client=client,
        )
        video_url = _extract_video_url(final)

    if not video_url:
        raise TokenHubError(
            "Pixverse completed task missing video URL",
            response=final,
        )

    result: dict[str, Any] = {
        "job_id": task_id,
        "model": model,
        "mode": mode,
        "status": _extract_status(final) or "completed",
        "video_url": video_url,
        "output_path": None,
        "duration": int(duration),
        "quality": quality,
        "aspect_ratio": aspect_ratio if mode == "t2v" else None,
    }
    if output_path is not None:
        session = client.session if client is not None else None
        path = download_video(video_url, output_path, session=session)
        result["output_path"] = str(path)
    return result
