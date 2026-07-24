"""Curated eRouter model catalog (plaza snapshot; not a full mirror).

status:
  ready   — callable via this package (chat only in phase 1)
  planned — listed for future wiring; do not call yet
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

Capability = Literal["chat", "image", "video"]
ModelStatus = Literal["ready", "planned"]


@dataclass(frozen=True)
class ERouterModel:
    id: str
    capability: Capability
    status: ModelStatus
    note: str = ""


# --- Chat / multimodal (OpenAI-compatible chat/completions) — ready ---
_CHAT_READY: tuple[ERouterModel, ...] = (
    ERouterModel("deepseek-v4-flash", "chat", "ready", "default smoke model"),
    ERouterModel("deepseek-v4-pro", "chat", "ready"),
    ERouterModel("azure/DeepSeek-V4-Flash", "chat", "ready"),
    ERouterModel("GLM-5.2", "chat", "ready"),
    ERouterModel("glm-5.2", "chat", "ready"),
    ERouterModel("azure/gpt-5.2-chat", "chat", "ready"),
    ERouterModel("gpt-5.4-nano", "chat", "ready"),
    ERouterModel("claude-haiku-4-5", "chat", "ready"),
    ERouterModel("claude-sonnet-4-6", "chat", "ready"),
    ERouterModel("gemini-2.5-flash", "chat", "ready"),
    ERouterModel("gemini-3.1-flash-lite", "chat", "ready"),
    ERouterModel("kimi-k2.6", "chat", "ready"),
    ERouterModel("qwen3.7-max", "chat", "ready"),
)

# --- Image — planned (catalog only; no generate path yet) ---
_IMAGE_PLANNED: tuple[ERouterModel, ...] = (
    ERouterModel("azure/gpt-image-2", "image", "planned"),
    ERouterModel("xai/grok-imagine-image", "image", "planned"),
    ERouterModel("xai/grok-imagine-image-pro", "image", "planned"),
)

# --- Video — planned (stub raises; no HTTP) ---
_VIDEO_PLANNED: tuple[ERouterModel, ...] = (
    ERouterModel("azure/sora-2", "video", "planned", "billed per video second"),
    ERouterModel("openai/grok-imagine-video", "video", "planned"),
    ERouterModel("openai/seedance-1.5-pro", "video", "planned"),
    ERouterModel("openai/seedance-2.0", "video", "planned"),
    ERouterModel("openai/seedance-2.0-fast", "video", "planned"),
)

# Append-only extension point for local overrides without editing the plaza shortlist.
EXTRA_MODELS: list[ERouterModel] = []

DEFAULT_CHAT_MODEL = "deepseek-v4-flash"


def all_models() -> tuple[ERouterModel, ...]:
    return _CHAT_READY + _IMAGE_PLANNED + _VIDEO_PLANNED + tuple(EXTRA_MODELS)


def list_models(
    *,
    capability: Capability | None = None,
    status: ModelStatus | None = None,
) -> list[ERouterModel]:
    models: Iterable[ERouterModel] = all_models()
    out: list[ERouterModel] = []
    for m in models:
        if capability is not None and m.capability != capability:
            continue
        if status is not None and m.status != status:
            continue
        out.append(m)
    return out


def get_model(model_id: str) -> ERouterModel | None:
    for m in all_models():
        if m.id == model_id:
            return m
    return None


def require_ready_chat_model(model_id: str) -> ERouterModel:
    """Allow any model id for chat HTTP (plaza may add ids); warn via catalog when known planned."""
    known = get_model(model_id)
    if known is not None and known.capability != "chat":
        raise ValueError(
            f"Model {model_id!r} is capability={known.capability!r}, not chat. "
            f"status={known.status}."
        )
    if known is not None and known.status != "ready":
        raise ValueError(
            f"Model {model_id!r} is status={known.status!r} (not ready for chat)."
        )
    # Unknown ids are still allowed for chat so the shortlist can be extended ad hoc.
    return known or ERouterModel(model_id, "chat", "ready", "ad-hoc / not in shortlist")
