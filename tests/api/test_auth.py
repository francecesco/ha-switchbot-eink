"""Test dell'autenticazione."""
from __future__ import annotations

import asyncio

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import mock_aiohttp_client

from custom_components.switchbot_eink.api.auth import CanvasAuth
from custom_components.switchbot_eink.api.errors import SwitchBotCanvasAuthError

ACCOUNT = "https://account.api.switchbot.net"
LOGIN = f"{ACCOUNT}/account/api/v1/user/login"
REFRESH = f"{ACCOUNT}/account/api/v1/user/token/refresh"
USERINFO = f"{ACCOUNT}/account/api/v1/user/userinfo"


@pytest.fixture
async def aioclient():
    with mock_aiohttp_client() as mocker:
        yield mocker


@pytest.fixture
async def session(aioclient):
    sess = aioclient.create_session(asyncio.get_running_loop())
    yield sess
    await sess.close()


async def test_login_restituisce_i_token(aioclient, session) -> None:
    aioclient.post(
        LOGIN,
        json={
            "statusCode": 100,
            "body": {
                "access_token": "AT",
                "refresh_token": "RT",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_expires_in": 86400,
            },
        },
    )
    auth = CanvasAuth(session, "eu")

    tokens = await auth.login("mario@example.test", "segreta")

    assert tokens.access_token == "AT"
    assert tokens.refresh_token == "RT"
    assert tokens.token_type == "Bearer"
    assert tokens.expires_in == 3600


async def test_login_invia_client_id_e_device_info(aioclient, session) -> None:
    aioclient.post(
        LOGIN,
        json={"statusCode": 100, "body": {"access_token": "AT", "refresh_token": "RT"}},
    )
    auth = CanvasAuth(session, "eu")

    await auth.login("mario@example.test", "segreta")
    _method, _url, body, _headers = aioclient.mock_calls[0]

    assert body["clientId"] == "pg6fbtxbi7q3o2n4zba852d5lh"
    assert body["grantType"] == "password"
    assert body["username"] == "mario@example.test"
    assert body["deviceInfo"] == {
        "deviceName": "Web",
        "deviceId": "hub-web",
        "appVersion": "0.0.0",
        "model": "Web",
    }


async def test_login_con_credenziali_errate_solleva_auth_error(aioclient, session) -> None:
    aioclient.post(LOGIN, json={"statusCode": 160, "message": "wrong password"})
    auth = CanvasAuth(session, "eu")

    with pytest.raises(SwitchBotCanvasAuthError):
        await auth.login("mario@example.test", "sbagliata")


async def test_refresh_invia_user_id_e_refresh_token(aioclient, session) -> None:
    aioclient.post(
        REFRESH,
        json={
            "statusCode": 100,
            "body": {"access_token": "AT2", "token_type": "Bearer", "expires_in": 3600},
        },
    )
    auth = CanvasAuth(session, "eu")

    tokens = await auth.refresh("user-1", "RT")
    _method, _url, body, _headers = aioclient.mock_calls[0]

    assert body == {
        "userId": "user-1",
        "refreshToken": "RT",
        "clientId": "pg6fbtxbi7q3o2n4zba852d5lh",
    }
    assert tokens.access_token == "AT2"
    assert tokens.refresh_token == "RT", "il refresh token va conservato, la risposta non lo ripete"


async def test_user_info_restituisce_id_ed_email(aioclient, session) -> None:
    aioclient.post(
        USERINFO,
        json={"statusCode": 100, "body": {"userID": "user-1", "email": "m@example.test"}},
    )
    auth = CanvasAuth(session, "eu")

    info = await auth.user_info("AT")

    assert info.user_id == "user-1"
    assert info.email == "m@example.test"


async def test_user_info_invia_header_senza_bearer_in_eu(aioclient, session) -> None:
    aioclient.post(USERINFO, json={"statusCode": 100, "body": {"userID": "u", "email": "e"}})
    auth = CanvasAuth(session, "eu")

    await auth.user_info("AT")
    _method, _url, _body, headers = aioclient.mock_calls[0]

    assert headers["Authorization"] == "AT"


async def test_user_info_invia_header_con_bearer_fuori_dalla_ue(aioclient, session) -> None:
    aioclient.post(USERINFO, json={"statusCode": 100, "body": {"userID": "u", "email": "e"}})
    auth = CanvasAuth(session, "us")

    await auth.user_info("AT")
    _method, _url, _body, headers = aioclient.mock_calls[0]

    assert headers["Authorization"] == "Bearer AT"
