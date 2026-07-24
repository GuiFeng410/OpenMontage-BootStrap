"""eRouter Chat via OpenAI-compatible /v1/chat/completions."""

from __future__ import annotations

from typing import Any

from tools._erouter.client import ERouterClient
from tools._erouter.models import DEFAULT_CHAT_MODEL, require_ready_chat_model


def chat_completions(
    messages: list[dict[str, Any]],
    *,
    model: str = DEFAULT_CHAT_MODEL,
    client: ERouterClient | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """POST chat/completions. Returns the raw JSON body."""
    require_ready_chat_model(model)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    payload.update(extra)

    api = client or ERouterClient()
    return api.post("/chat/completions", payload)


def extract_assistant_text(response: dict[str, Any]) -> str:
    """Best-effort plain text from a chat completions response."""
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(content or "")
