"""Client HTTP asincrono per il backend SwitchBot."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .errors import SwitchBotCanvasApiError, SwitchBotCanvasAuthError

AuthProvider = Callable[[], str | None]
RefreshCallback = Callable[[], Awaitable[bool]]
Unwrapper = Callable[[object], Any]


class CanvasHttp:
    """POST JSON verso un base URL, con un solo tentativo di refresh su 401."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        unwrap: Unwrapper,
        auth_provider: AuthProvider | None = None,
        on_unauthorized: RefreshCallback | None = None,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._unwrap = unwrap
        self._auth_provider = auth_provider
        self._on_unauthorized = on_unauthorized

    async def request(self, path: str, body: dict[str, Any] | None = None) -> Any:
        status, payload = await self._post_once(path, body)

        if status == 401 and self._on_unauthorized is not None:
            if not await self._on_unauthorized():
                raise SwitchBotCanvasAuthError("Refresh del token fallito")
            status, payload = await self._post_once(path, body)

        if status == 401:
            raise SwitchBotCanvasAuthError("Il backend ha risposto 401")
        if status >= 400:
            raise SwitchBotCanvasApiError(status, f"HTTP {status}")

        return self._unwrap(payload)

    async def _post_once(
        self, path: str, body: dict[str, Any] | None
    ) -> tuple[int, object]:
        headers = {"content-type": "application/json"}
        if self._auth_provider is not None:
            token = self._auth_provider()
            if token:
                headers["Authorization"] = token

        try:
            async with self._session.post(
                f"{self._base_url}{path}", headers=headers, json=body
            ) as response:
                if response.status >= 400:
                    return response.status, None
                return response.status, await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise SwitchBotCanvasApiError(0, f"Errore di rete: {err}") from err
