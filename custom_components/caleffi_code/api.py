"""HTTP client for the Caleffi CODE cloud API."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any
from urllib.parse import urlsplit

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import APP_VERSION

_LOGGER = logging.getLogger(__name__)


class CaleffiApiError(Exception):
    """Raised when the Caleffi API returns an error."""

    def __init__(
        self, message: str, status: int | None = None, code: str | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class CaleffiApi:
    """Make authenticated requests to the Caleffi CODE API."""

    def __init__(
        self,
        hass: HomeAssistant,
        base_url: str,
        email: str,
        refresh_token: str | None = None,
        on_refresh_token: Callable[[str], None | Awaitable[None]] | None = None,
    ) -> None:
        parsed_url = urlsplit(base_url)
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("The Caleffi CODE API URL must use HTTPS")

        self._session = async_get_clientsession(hass)
        self._base_url = base_url.rstrip("/") + "/"
        self._email = email
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._on_refresh_token = on_refresh_token
        self._refresh_lock = asyncio.Lock()

    async def async_login(self, password: str) -> dict[str, Any]:
        """Log in and return the API token response."""
        result = await self._request(
            "POST",
            "user/login",
            json_body={"email": self._email, "password": password},
            authenticated=False,
        )
        await self._set_tokens(result)
        return result

    async def async_refresh_access_token(self) -> None:
        """Exchange the stored refresh token for a new access token."""
        if not self._refresh_token:
            raise CaleffiApiError("No Caleffi CODE refresh token is configured", 401)

        async with self._refresh_lock:
            result = await self._request(
                "POST",
                "token",
                json_body={
                    "refresh_token": self._refresh_token,
                    "email": self._email,
                },
                headers={"x-refresh-tkn": "false"},
                authenticated=False,
            )
            await self._set_tokens(result)

    async def async_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Make an authenticated API request, refreshing once if needed."""
        try:
            return await self._request(
                method,
                path,
                params=params,
                json_body=json_body,
            )
        except CaleffiApiError as err:
            if err.status not in (400, 401) or not self._is_expired_token(err):
                raise

        await self.async_refresh_access_token()
        return await self._request(method, path, params=params, json_body=json_body)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        authenticated: bool = True,
    ) -> Any:
        request_headers = {
            "User-Agent": "Android",
            "x-app-version": APP_VERSION,
            **(headers or {}),
        }
        if authenticated and self._access_token:
            request_headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            async with self._session.request(
                method,
                self._base_url + path.lstrip("/"),
                params=params,
                json=json_body,
                headers=request_headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                try:
                    payload = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    payload = None

                if response.status < 200 or response.status >= 300:
                    message = self._error_message(payload) or (
                        f"Caleffi CODE API returned HTTP {response.status}"
                    )
                    raise CaleffiApiError(
                        message,
                        response.status,
                        self._error_code(payload),
                    )
                return payload
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning(
                "Unable to connect to the Caleffi CODE API (%s): %s",
                type(err).__name__,
                err,
            )
            raise CaleffiApiError("Cannot connect to the Caleffi CODE API") from err

    async def _set_tokens(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            raise CaleffiApiError("Caleffi CODE returned an invalid token response")

        jwt = payload.get("jwt")
        access_token = jwt.get("token") if isinstance(jwt, dict) else None
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            raise CaleffiApiError("Caleffi CODE returned an incomplete token response")

        self._access_token = access_token
        self._refresh_token = refresh_token
        if self._on_refresh_token is not None:
            result = self._on_refresh_token(refresh_token)
            if isawaitable(result):
                await result

    @staticmethod
    def _error_message(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("description")
            if isinstance(message, str):
                return message
        message = payload.get("message")
        return message if isinstance(message, str) else None

    @staticmethod
    def _error_code(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        code = error.get("code") if isinstance(error, dict) else payload.get("code")
        return str(code) if code is not None else None

    @staticmethod
    def _is_expired_token(err: CaleffiApiError) -> bool:
        error = f"{err.code or ''} {err}".lower().replace(" ", "_")
        return (
            "token_expired" in error
            or "jwt_expired" in error
            or ("token" in error and "expired" in error)
        )
