"""Agnes AI shared client helpers (API key, base URL, image Data URI)."""

from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path

AGNES_BASE = "https://apihub.agnes-ai.com"


def get_agnes_api_key() -> str | None:
    """Return Agnes API key from AGNES_API_KEY or AGNES_AI_API_KEY."""
    key = (os.environ.get("AGNES_API_KEY") or os.environ.get("AGNES_AI_API_KEY") or "").strip()
    return key or None


def file_to_data_uri(path_str: str) -> str:
    """Encode a local image file as a Data URI for Agnes image/video inputs."""
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        mime_type = "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def normalize_image_ref(url_value: str | None, path_value: str | None) -> str | None:
    """Return a public URL or Data URI for Agnes image inputs."""
    if url_value:
        return str(url_value)
    if path_value:
        return file_to_data_uri(str(path_value))
    return None
