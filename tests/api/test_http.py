"""Test del client HTTP."""
from __future__ import annotations

import asyncio

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
    mock_aiohttp_client,
)
from yarl import URL

from custom_components.switchbot_eink.api.envelope import unwrap_backend
from custom_components.switchbot_eink.api.errors import (
    SwitchBotCanvasApiError,
    SwitchBotCanvasAuthError,
)
from custom_components.switchbot_eink.api.http import CanvasHttp
from tests.api.helpers import response_sequence

BASE = "https://example.test/productbiz"
PING = f"{BASE}/ping"


def json_response(payload, status=200):
    return AiohttpClientMockResponse("post", URL(PING), status=status, json=payload)


def empty_response(status):
    return AiohttpClientMockResponse("post", URL(PING), status=status)


@pytest.fixture
async def aioclient():
    with mock_aiohttp_client() as mocker:
        yield mocker


@pytest.fixture
async def session(aioclient):
    sess = aioclient.create_session(asyncio.get_running_loop())
    yield sess
    await sess.close()


async def test_request_invia_post_json_e_scarta_envelope(aioclient, session) -> None:
    aioclient.post(PING, json={"resultCode": 100, "data": {"pong": 1}})
    http = CanvasHttp(session, BASE, unwrap_backend)

    assert await http.request("/ping", {"a": 1}) == {"pong": 1}


async def test_request_invia_il_body_come_json(aioclient, session) -> None:
    aioclient.post(PING, json={"resultCode": 100, "data": None})
    http = CanvasHttp(session, BASE, unwrap_backend)

    await http.request("/ping", {"a": 1})
    _method, _url, data, _headers = aioclient.mock_calls[0]

    assert data == {"a": 1}


async def test_request_aggiunge_header_authorization(aioclient, session) -> None:
    aioclient.post(PING, json={"resultCode": 100, "data": None})
    http = CanvasHttp(session, BASE, unwrap_backend, auth_provider=lambda: "tok")

    await http.request("/ping")
    _method, _url, _data, headers = aioclient.mock_calls[0]

    assert headers["Authorization"] == "tok"


async def test_request_omette_authorization_senza_provider(aioclient, session) -> None:
    aioclient.post(PING, json={"resultCode": 100, "data": None})
    http = CanvasHttp(session, BASE, unwrap_backend)

    await http.request("/ping")
    _method, _url, _data, headers = aioclient.mock_calls[0]

    assert "Authorization" not in headers


async def test_401_http_tenta_il_refresh_e_ripete_una_volta(aioclient, session) -> None:
    chiamate: list[str] = []

    async def refresh() -> bool:
        chiamate.append("refresh")
        return True

    aioclient.post(
        PING,
        side_effect=response_sequence(
            empty_response(401),
            json_response({"resultCode": 100, "data": {"ok": True}}),
        ),
    )
    http = CanvasHttp(
        session, BASE, unwrap_backend, auth_provider=lambda: "tok", on_unauthorized=refresh
    )

    assert await http.request("/ping") == {"ok": True}
    assert chiamate == ["refresh"]


async def test_401_due_volte_solleva_auth_error(aioclient, session) -> None:
    async def refresh() -> bool:
        return True

    aioclient.post(
        PING,
        side_effect=response_sequence(empty_response(401), empty_response(401)),
    )
    http = CanvasHttp(
        session, BASE, unwrap_backend, auth_provider=lambda: "tok", on_unauthorized=refresh
    )

    with pytest.raises(SwitchBotCanvasAuthError):
        await http.request("/ping")


async def test_401_senza_refresh_disponibile_solleva_subito(aioclient, session) -> None:
    aioclient.post(PING, status=401)
    http = CanvasHttp(session, BASE, unwrap_backend, auth_provider=lambda: "tok")

    with pytest.raises(SwitchBotCanvasAuthError):
        await http.request("/ping")


async def test_refresh_fallito_solleva_auth_error(aioclient, session) -> None:
    async def refresh() -> bool:
        return False

    aioclient.post(PING, status=401)
    http = CanvasHttp(
        session, BASE, unwrap_backend, auth_provider=lambda: "tok", on_unauthorized=refresh
    )

    with pytest.raises(SwitchBotCanvasAuthError):
        await http.request("/ping")


async def test_errore_http_generico_solleva_api_error(aioclient, session) -> None:
    aioclient.post(PING, status=500)
    http = CanvasHttp(session, BASE, unwrap_backend)

    with pytest.raises(SwitchBotCanvasApiError):
        await http.request("/ping")
