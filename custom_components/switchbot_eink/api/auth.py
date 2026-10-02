"""Login, refresh del token e profilo utente."""
from __future__ import annotations

from dataclasses import dataclass

import aiohttp

from .const import (
    ACCOUNT_BASE_URL,
    CLIENT_ID,
    DEVICE_INFO,
    PATH_LOGIN,
    PATH_REFRESH,
    PATH_USERINFO,
)
from .envelope import build_auth_header, unwrap_account
from .http import CanvasHttp


@dataclass(frozen=True, slots=True)
class Tokens:
    """Token restituiti dall'account service."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 0
    refresh_expires_in: int = 0


@dataclass(frozen=True, slots=True)
class Credentials:
    """Email e password dell'account, per rifare il login senza l'utente.

    Il refresh token ha una vita limitata e `/token/refresh` non ne restituisce
    mai uno nuovo (verificato nel bundle dell'editor web ufficiale): quando
    scade, l'unico modo di ottenere token nuovi e' un login completo.
    """

    username: str
    password: str


@dataclass(frozen=True, slots=True)
class UserInfo:
    """Identità dell'utente autenticato."""

    user_id: str
    email: str


class CanvasAuth:
    """Dialoga con https://account.api.switchbot.net."""

    def __init__(self, session: aiohttp.ClientSession, region: str) -> None:
        self._session = session
        self._region = region

    def _http(self, auth_header: str | None = None) -> CanvasHttp:
        return CanvasHttp(
            self._session,
            ACCOUNT_BASE_URL,
            unwrap_account,
            auth_provider=(lambda: auth_header) if auth_header else None,
        )

    async def login(self, username: str, password: str) -> Tokens:
        """Autentica con email e password e restituisce i token."""
        body = await self._http().request(
            PATH_LOGIN,
            {
                "username": username,
                "password": password,
                "deviceInfo": DEVICE_INFO,
                "grantType": "password",
                "clientId": CLIENT_ID,
            },
        )
        return Tokens(
            access_token=body["access_token"],
            refresh_token=body["refresh_token"],
            token_type=body.get("token_type", "Bearer"),
            expires_in=int(body.get("expires_in", 0)),
            refresh_expires_in=int(body.get("refresh_expires_in", 0)),
        )

    async def refresh(self, user_id: str, refresh_token: str) -> Tokens:
        """Rinnova l'access token. Il refresh token non viene ripetuto dalla risposta."""
        body = await self._http().request(
            PATH_REFRESH,
            {"userId": user_id, "refreshToken": refresh_token, "clientId": CLIENT_ID},
        )
        return Tokens(
            access_token=body["access_token"],
            refresh_token=refresh_token,
            token_type=body.get("token_type", "Bearer"),
            expires_in=int(body.get("expires_in", 0)),
        )

    async def user_info(self, access_token: str, token_type: str = "Bearer") -> UserInfo:
        """Recupera userID ed email, necessari per il refresh."""
        header = build_auth_header(access_token, token_type, self._region)
        body = await self._http(header).request(PATH_USERINFO)
        return UserInfo(user_id=str(body["userID"]), email=str(body.get("email", "")))
