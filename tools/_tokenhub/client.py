"""Tencent TokenHub shared config and HTTP client — independent of Agnes and eRouter."""

from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_BASE_URL = "https://tokenhub.tencentmaas.com/v1"


class TokenHubError(RuntimeError):
    """TokenHub API or configuration error."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        response: object = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.response = response


class TokenHubNotReadyError(TokenHubError):
    """Capability is catalogued / configured but generation is not implemented yet."""


def get_tokenhub_api_key() -> str | None:
    """Return API key from TOKENHUB_API_KEY (or TENCENT_TOKENHUB_API_KEY alias)."""
    key = (
        os.environ.get("TOKENHUB_API_KEY")
        or os.environ.get("TENCENT_TOKENHUB_API_KEY")
        or ""
    ).strip()
    return key or None


def get_tokenhub_base_url() -> str:
    """Base URL ending without trailing slash (…/v1)."""
    raw = (os.environ.get("TOKENHUB_BASE_URL") or DEFAULT_BASE_URL).strip()
    return raw.rstrip("/")


class TokenHubClient:
    """Synchronous client for TokenHub OpenAI-compatible video endpoints."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else get_tokenhub_api_key()
        self.base_url = (base_url or get_tokenhub_base_url()).rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise TokenHubError(
                "TOKENHUB_API_KEY is not set. Add your TokenHub Bearer key to .env "
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
        timeout: float | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.request(
                method.upper(),
                url,
                headers=self._headers(),
                json=json,
                params=params,
                timeout=self.timeout if timeout is None else timeout,
            )
        except requests.RequestException as exc:
            raise TokenHubError(f"TokenHub request failed: {exc}") from exc

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
            raise TokenHubError(
                f"TokenHub HTTP {response.status_code}: {message}",
                http_status=response.status_code,
                response=payload,
            )

        if not isinstance(payload, dict):
            raise TokenHubError(
                f"TokenHub returned non-object JSON: {type(payload).__name__}",
                http_status=response.status_code,
                response=payload,
            )
        return payload

    def post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self.request("POST", path, json=payload, timeout=timeout)

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self.request("GET", path, params=params, timeout=timeout)
