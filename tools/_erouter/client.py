"""eRouter (edensoft) shared HTTP client — independent of Agnes."""

from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_BASE_URL = "https://aimiddleplatform.edensoft.ai/v1"


class ERouterError(RuntimeError):
    """eRouter API or configuration error."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        response: Any = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.response = response


class ERouterNotReadyError(ERouterError):
    """Capability is catalogued but not implemented yet (e.g. video)."""


def get_erouter_api_key() -> str | None:
    """Return Proxy Key from EROUTER_API_KEY (or EROUTER_PROXY_KEY alias)."""
    key = (
        os.environ.get("EROUTER_API_KEY")
        or os.environ.get("EROUTER_PROXY_KEY")
        or ""
    ).strip()
    return key or None


def get_erouter_base_url() -> str:
    """Base URL ending without trailing slash (…/v1)."""
    raw = (os.environ.get("EROUTER_BASE_URL") or DEFAULT_BASE_URL).strip()
    return raw.rstrip("/")


class ERouterClient:
    """Synchronous OpenAI-compatible client for eRouter."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else get_erouter_api_key()
        self.base_url = (base_url or get_erouter_base_url()).rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ERouterError(
                "EROUTER_API_KEY is not set. Add your eRouter Proxy Key to .env "
                "(see .env.example). Do not commit the key.",
                http_status=401,
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.request(
                method.upper(),
                url,
                headers=self._headers(),
                json=json,
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ERouterError(f"eRouter request failed: {exc}") from exc

        try:
            payload = response.json() if response.content else {}
        except ValueError:
            payload = {"raw": response.text}

        if response.status_code >= 400:
            detail = payload.get("error") if isinstance(payload, dict) else payload
            if isinstance(detail, dict):
                message = detail.get("message") or detail.get("msg") or str(detail)
            else:
                message = str(detail) if detail else response.text[:500]
            raise ERouterError(
                f"eRouter HTTP {response.status_code}: {message}",
                http_status=response.status_code,
                response=payload,
            )

        if not isinstance(payload, dict):
            raise ERouterError(
                f"eRouter returned non-object JSON: {type(payload).__name__}",
                http_status=response.status_code,
                response=payload,
            )
        return payload

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", path, json=payload)

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("GET", path, params=params)
