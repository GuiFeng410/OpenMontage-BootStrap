"""TokenHub Pixverse video — T2V / I2V via /wand/pixverse/* (P0).

Reference / start-end modes are deferred (P2).
I2V requires a public http(s) image URL (img_id); local base64 is not wired yet.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit, urlunsplit

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

# Do NOT treat numeric status alone as terminal — Pixverse may set status=5
# before the CDN URL is actually downloadable.
_TERMINAL_OK = frozenset(
    {
        "completed",
        "succeed",
        "success",
        "succeeded",
        "done",
    }
)
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


def _nested_dicts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """TokenHub wand often wraps fields in Resp / data / result."""
    out: list[dict[str, Any]] = [payload]
    for key in ("Resp", "resp", "data", "result", "Result"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            out.append(nested)
    return out


def _wand_err_code(payload: dict[str, Any]) -> int | None:
    if "ErrCode" not in payload and "err_code" not in payload:
        return None
    raw = payload.get("ErrCode", payload.get("err_code"))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _extract_task_id(payload: dict[str, Any]) -> str:
    keys = ("task_id", "video_id", "id", "job_id", "TaskId", "VideoId")
    for obj in _nested_dicts(payload):
        for key in keys:
            raw = obj.get(key)
            if raw:
                return str(raw)
    return ""


def _extract_status(payload: dict[str, Any]) -> str:
    # Wand envelope: ErrCode!=0 is failure; ErrCode==0 alone is not terminal.
    err = _wand_err_code(payload)
    if err is not None and err != 0:
        return "failed"

    keys = ("status", "state", "task_status", "Status", "State", "video_status")
    for obj in _nested_dicts(payload):
        for key in keys:
            raw = obj.get(key)
            if raw is not None and str(raw).strip():
                return str(raw).strip().lower()
    return ""


def _extract_video_url(payload: dict[str, Any]) -> str:
    candidates: list[Any] = []
    url_keys = (
        "video_url",
        "url",
        "output_url",
        "download_url",
        "VideoUrl",
        "OutputUrl",
        "video",
    )
    for obj in _nested_dicts(payload):
        for key in url_keys:
            candidates.append(obj.get(key))
        output = obj.get("output") or obj.get("Output")
        if isinstance(output, dict):
            for key in url_keys:
                candidates.append(output.get(key))
        elif isinstance(output, str):
            candidates.append(output)

    for raw in candidates:
        if isinstance(raw, str) and raw.startswith(("http://", "https://")):
            return _normalize_media_url(raw)
        if isinstance(raw, list) and raw:
            first = raw[0]
            if isinstance(first, str) and first.startswith(("http://", "https://")):
                return _normalize_media_url(first)
            if isinstance(first, dict):
                for key in ("url", "video_url", "VideoUrl"):
                    nested = first.get(key)
                    if isinstance(nested, str) and nested.startswith(("http://", "https://")):
                        return _normalize_media_url(nested)
    return ""


def _normalize_media_url(url: str) -> str:
    """Decode over-encoded path segments (e.g. pixverse%2Fmp4 → pixverse/mp4)."""
    parts = urlsplit(url.strip())
    path = unquote(parts.path)
    # Some CDNs still 404 if query/fragment odd; keep as-is after path unquote.
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _error_message(payload: dict[str, Any]) -> str:
    for obj in _nested_dicts(payload):
        for key in ("ErrMsg", "message", "msg", "error", "fail_reason"):
            raw = obj.get(key)
            if isinstance(raw, dict):
                nested = raw.get("message") or raw.get("msg") or raw.get("error")
                if nested:
                    return str(nested)
            elif raw and str(raw).lower() not in {"success", "ok"}:
                return str(raw)
    err = _wand_err_code(payload)
    if err is not None and err != 0:
        return f"ErrCode={err}"
    return ""


def _submit_ok(payload: dict[str, Any]) -> bool:
    err = _wand_err_code(payload)
    if err is not None:
        return err == 0 and bool(_extract_task_id(payload))
    return bool(_extract_task_id(payload))


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
    first = True
    while True:
        last = query_pixverse_task(task_id, client=client)
        status = _extract_status(last)
        video_url = _extract_video_url(last)
        if first:
            # Help diagnose unknown envelopes without dumping large payloads.
            print(
                f"pixverse first poll keys={list(last.keys())} "
                f"resp_keys={list((last.get('Resp') or last.get('resp') or {}).keys()) if isinstance(last.get('Resp') or last.get('resp'), dict) else []}",
                flush=True,
            )
            first = False
        print(
            f"pixverse poll id={task_id} status={status or '?'} has_url={bool(video_url)}",
            flush=True,
        )
        if status in _TERMINAL_FAIL:
            raise TokenHubError(
                f"Pixverse task {task_id} ended with status={status}: {_error_message(last)}",
                response=last,
            )
        # Prefer waiting for a real URL; numeric status alone is unreliable.
        if video_url or status in _TERMINAL_OK:
            return last
        if time.monotonic() >= deadline:
            raise TokenHubError(
                f"Pixverse task {task_id} timed out after {timeout_seconds:.0f}s",
                response=last,
            )
        time.sleep(poll_interval_seconds)


def _download_with_cdn_retry(
    url: str,
    output_path: str | Path,
    *,
    session=None,
    attempts: int = 12,
    wait_seconds: float = 5.0,
) -> Path:
    """Pixverse often returns a URL before the CDN object is ready (404 then 200)."""
    last_err: Exception | None = None
    for i in range(max(1, attempts)):
        try:
            return download_video(url, output_path, session=session)
        except TokenHubError as exc:
            last_err = exc
            msg = str(exc)
            if "404" not in msg and "Not Found" not in msg:
                raise
            print(
                f"pixverse download 404 retry {i + 1}/{attempts} wait={wait_seconds}s",
                flush=True,
            )
            time.sleep(wait_seconds)
    raise TokenHubError(
        f"Pixverse video URL still not downloadable after retries: {url}"
    ) from last_err


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
    if status in _TERMINAL_FAIL or not _submit_ok(submit) or not task_id:
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
        path = _download_with_cdn_retry(video_url, output_path, session=session)
        result["output_path"] = str(path)
    return result
