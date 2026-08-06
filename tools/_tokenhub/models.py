"""Curated Tencent TokenHub video model catalog (extensible).

status:
  configured — Key gate + 表② may offer; hy-video-1.5 generation is wired
  planned    — registered for later; do not offer as primary pick

Append to EXTRA_MODELS locally to add models without editing the shortlist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

Capability = Literal["video"]
ModelStatus = Literal["configured", "planned"]


@dataclass(frozen=True)
class TokenHubModel:
    id: str
    capability: Capability
    status: ModelStatus
    note: str = ""


_VIDEO_MODELS: tuple[TokenHubModel, ...] = (
    TokenHubModel(
        "hy-video-1.5",
        "video",
        "configured",
        "混元 HY-Video（T2V/I2V）；可出片；约720p；默认并发1；无自定义时长",
    ),
    TokenHubModel("yt-video-2.0", "video", "planned", "多图图生视频通道"),
    TokenHubModel("yt-video-fx", "video", "planned", "视频特效模型"),
    TokenHubModel("yt-video-humanactor", "video", "planned", "数字人相关"),
)

EXTRA_MODELS: list[TokenHubModel] = []

DEFAULT_VIDEO_MODEL = "hy-video-1.5"


def all_models() -> tuple[TokenHubModel, ...]:
    return _VIDEO_MODELS + tuple(EXTRA_MODELS)


def list_models(
    *,
    capability: Capability | None = None,
    status: ModelStatus | None = None,
) -> list[TokenHubModel]:
    models: Iterable[TokenHubModel] = all_models()
    out: list[TokenHubModel] = []
    for m in models:
        if capability is not None and m.capability != capability:
            continue
        if status is not None and m.status != status:
            continue
        out.append(m)
    return out


def get_model(model_id: str) -> TokenHubModel | None:
    for m in all_models():
        if m.id == model_id:
            return m
    return None


def configured_video_models() -> list[str]:
    return [m.id for m in list_models(capability="video", status="configured")]


def planned_video_models() -> list[str]:
    return [m.id for m in list_models(capability="video", status="planned")]
