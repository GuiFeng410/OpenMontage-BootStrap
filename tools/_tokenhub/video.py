"""TokenHub video generation — submit / query / download for hy-video-1.5."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import requests

from tools._tokenhub.client import (
    TokenHubClient,
    TokenHubError,
    TokenHubNotReadyError,
    get_tokenhub_api_key,
)
from tools._tokenhub.models import DEFAULT_VIDEO_MODEL, get_model

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "canceled", "error"})


def _file_to_base64(path_str: str) -> str:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path_str}")
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _image_payload(
    image_path: str | None = None,
    image_url: str | None = None,
) -> dict[str, str] | None:
    if image_url:
        url = str(image_url).strip()
        if not url.startswith(("http://", "https://")):
            raise TokenHubError("image_url must be an http(s) URL for TokenHub I2V")
        return {"url": url}
    if image_path:
        return {"base64": _file_to_base64(image_path)}
    return None


def submit_video_job(
    prompt: str,
    *,
    model: str | None = None,
    image_path: str | None = None,
    image_url: str | None = None,
    resolution: str = "720p",
    logo_add: int = 0,
    client: TokenHubClient | None = None,
) -> dict[str, Any]:
    """POST /api/video/submit. Returns raw JSON including task id."""
    model_id = model or DEFAULT_VIDEO_MODEL
    known = get_model(model_id)
    if known is not None and known.status == "planned":
        from tools._tokenhub.models import configured_video_models

        ready = ", ".join(configured_video_models()) or DEFAULT_VIDEO_MODEL
        raise TokenHubNotReadyError(
            f"TokenHub model {model_id!r} is planned (not wired). Use one of: {ready}."
        )

    from tools._tokenhub.pixverse import is_pixverse_model

    if is_pixverse_model(model_id):
        raise TokenHubError(
            f"Model {model_id!r} uses Pixverse (/wand/pixverse/*). "
            "Call generate_video(...) or tools._tokenhub.pixverse helpers, "
            "not submit_video_job (Hunyuan /api/video/*)."
        )

    payload: dict[str, Any] = {
        "model": model_id,
        "prompt": prompt,
        "resolution": resolution,
        "logo_add": logo_add,
    }
    image = _image_payload(image_path, image_url)
    if image:
        payload["image"] = image

    api = client or TokenHubClient()
    return api.post("/api/video/submit", payload)


def query_video_job(
    job_id: str,
    *,
    model: str | None = None,
    client: TokenHubClient | None = None,
) -> dict[str, Any]:
    """POST /api/video/query. Returns raw JSON including status and data.url."""
    model_id = model or DEFAULT_VIDEO_MODEL
    get_model(model_id)  # catalog touch (parity with prior implementation)
    api = client or TokenHubClient()
    return api.post("/api/video/query", {"model": model_id, "id": job_id})


def poll_video_job(
    job_id: str,
    *,
    model: str | None = None,
    poll_interval_seconds: float = 8.0,
    timeout_seconds: float = 900.0,
    client: TokenHubClient | None = None,
) -> dict[str, Any]:
    """Poll until completed or failed. Returns final query payload."""
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while True:
        last = query_video_job(job_id, model=model, client=client)
        status = str(last.get("status") or "").lower()
        progress = last.get("progress")
        print(
            f"tokenhub poll id={job_id} status={status} progress={progress}",
            flush=True,
        )
        if status in _TERMINAL_STATUSES:
            if status == "completed":
                return last
            message = last.get("message") or last.get("error") or ""
            raise TokenHubError(
                f"TokenHub job {job_id} ended with status={status}: {message}",
                response=last,
            )
        if time.monotonic() >= deadline:
            raise TokenHubError(
                f"TokenHub job {job_id} timed out after {timeout_seconds:.0f}s",
                response=last,
            )
        time.sleep(poll_interval_seconds)


def download_video(
    url: str,
    output_path: str | Path,
    *,
    session: requests.Session | None = None,
) -> Path:
    """Download mp4 from completed job URL."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    http = session or requests.Session()
    try:
        response = http.get(url, timeout=300, stream=True)
        response.raise_for_status()
        with out.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=262144):
                if chunk:
                    handle.write(chunk)
    except requests.RequestException as exc:
        raise TokenHubError(f"TokenHub video download failed: {exc}") from exc

    if not out.exists() or out.stat().st_size < 10000:
        raise TokenHubError(f"Downloaded video too small or missing: {out}")
    return out


def generate_video(
    prompt: str,
    *,
    model: str | None = None,
    image_path: str | None = None,
    image_url: str | None = None,
    project_id: str | None = None,
    user_authorized_upload: bool = False,
    output_path: str | Path | None = None,
    resolution: str = "720p",
    logo_add: int = 0,
    duration: int | None = None,
    quality: str | None = None,
    aspect_ratio: str | None = None,
    generate_audio_switch: bool | None = None,
    poll_interval_seconds: float = 8.0,
    timeout_seconds: float = 900.0,
    client: TokenHubClient | None = None,
) -> dict[str, Any]:
    """Submit, poll, optionally download. Returns summary dict.

    Routes ``pixverse-*`` models to ``tools._tokenhub.pixverse``; otherwise
    uses Hunyuan ``/api/video/*`` (``hy-video-1.5``).
    """
    if not get_tokenhub_api_key() and (client is None or not client.api_key):
        raise TokenHubError("TOKENHUB_API_KEY is not set", http_status=401)

    model_id = model or DEFAULT_VIDEO_MODEL

    from tools._tokenhub.pixverse import (
        PIXVERSE_DEFAULT_GENERATE_AUDIO,
        PIXVERSE_DEFAULT_QUALITY,
        generate_pixverse_video,
        is_pixverse_model,
    )

    if is_pixverse_model(model_id):
        mode = "i2v" if (image_url or image_path) else "t2v"
        return generate_pixverse_video(
            prompt,
            mode=mode,  # type: ignore[arg-type]
            model=model_id,
            image_url=image_url,
            image_path=image_path,
            project_id=project_id,
            user_authorized_upload=user_authorized_upload,
            output_path=output_path,
            duration=int(duration) if duration is not None else 5,
            quality=quality or PIXVERSE_DEFAULT_QUALITY,
            aspect_ratio=aspect_ratio or "16:9",
            generate_audio_switch=(
                PIXVERSE_DEFAULT_GENERATE_AUDIO
                if generate_audio_switch is None
                else bool(generate_audio_switch)
            ),
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
            client=client,
        )

    submit = submit_video_job(
        prompt,
        model=model_id,
        image_path=image_path,
        image_url=image_url,
        resolution=resolution,
        logo_add=logo_add,
        client=client,
    )
    job_id = str(submit.get("id") or "")
    status = str(submit.get("status") or "").lower()
    if status in frozenset({"failed", "error"}) or not job_id:
        err = submit.get("error") if isinstance(submit.get("error"), dict) else {}
        message = ""
        if isinstance(err, dict):
            message = str(err.get("message") or err.get("msg") or err)
        message = message or str(submit.get("message") or submit.get("error") or submit)
        raise TokenHubError(
            f"TokenHub submit failed: {message}",
            response=submit,
        )

    final = poll_video_job(
        job_id,
        model=model_id,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
        client=client,
    )
    data = final.get("data") if isinstance(final.get("data"), dict) else {}
    video_url = str((data or {}).get("url") or "")
    if not video_url:
        raise TokenHubError(
            "TokenHub completed job missing data.url",
            response=final,
        )

    result: dict[str, Any] = {
        "job_id": job_id,
        "model": model_id,
        "status": str(final.get("status") or "completed"),
        "video_url": video_url,
        "output_path": None,
    }
    if output_path is not None:
        session = client.session if client is not None else None
        path = download_video(video_url, output_path, session=session)
        result["output_path"] = str(path)
    return result
