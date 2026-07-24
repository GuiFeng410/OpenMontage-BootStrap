"""eRouter independent gateway layer (phase 1: chat smoke + model catalog).

Agnes remains separate under tools/_agnes/. Do not rewrite Agnes base URLs here.
"""

from tools._erouter.chat import chat_completions, extract_assistant_text
from tools._erouter.client import (
    DEFAULT_BASE_URL,
    ERouterClient,
    ERouterError,
    ERouterNotReadyError,
    get_erouter_api_key,
    get_erouter_base_url,
)
from tools._erouter.models import (
    DEFAULT_CHAT_MODEL,
    EXTRA_MODELS,
    ERouterModel,
    all_models,
    get_model,
    list_models,
)
from tools._erouter.video import generate_video, planned_video_models

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_CHAT_MODEL",
    "EXTRA_MODELS",
    "ERouterClient",
    "ERouterError",
    "ERouterModel",
    "ERouterNotReadyError",
    "all_models",
    "chat_completions",
    "extract_assistant_text",
    "generate_video",
    "get_erouter_api_key",
    "get_erouter_base_url",
    "get_model",
    "list_models",
    "planned_video_models",
]
