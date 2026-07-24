"""eRouter video stub — models are catalogued; generation is not ready (phase 1)."""

from __future__ import annotations

from typing import Any

from tools._erouter.client import ERouterNotReadyError
from tools._erouter.models import list_models


def planned_video_models() -> list[str]:
    return [m.id for m in list_models(capability="video", status="planned")]


def generate_video(*_args: Any, **kwargs: Any) -> None:
    """Hard-fail placeholder. Does not send HTTP.

    Collect eRouter-domain P0 (path, body, poll/download, I2V) before implementing.
    """
    model = kwargs.get("model", "<unspecified>")
    planned = ", ".join(planned_video_models()) or "(none listed)"
    raise ERouterNotReadyError(
        "eRouter video generation is not ready (phase 1 stub). "
        f"Requested model={model!r}. Planned catalog ids: {planned}. "
        "Do not call until P0 video API details are collected under the eRouter domain. "
        "No HTTP request was sent."
    )
