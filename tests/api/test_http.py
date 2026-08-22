"""Test del client HTTP."""
from __future__ import annotations

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.switchbot_eink.api.envelope import unwrap_backend
from custom_components.switchbot_eink.api.errors import SwitchBotCanvasAuthError
from custom_components.switchbot_eink.api.http import CanvasHttp

BASE = "https://example.test/productbiz"


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as sess:
        yield sess


async def test_request_invia_post_json_e_scarta_envelope(session) -> None:
    http = CanvasHttp(session, BASE, unwrap_backend)
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", payload={"resultCode": 100, "data": {"pong": 1}})
        assert await http.request("/ping", {"a": 1}) == {"pong": 1}


async def test_request_aggiunge_header_authorization(session) -> None:
    http = CanvasHttp(session, BASE, unwrap_backend, auth_provider=lambda: "tok")
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", payload={"resultCode": 100, "data": None})
        await http.request("/ping")
        request = next(iter(mocked.requests.values()))[0]
        assert request.kwargs["headers"]["Authorization"] == "tok"


async def test_request_omette_authorization_senza_provider(session) -> None:
    http = CanvasHttp(session, BASE, unwrap_backend)
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", payload={"resultCode": 100, "data": None})
        await http.request("/ping")
        request = next(iter(mocked.requests.values()))[0]
        assert "Authorization" not in request.kwargs["headers"]


async def test_401_http_tenta_il_refresh_e_ripete_una_volta(session) -> None:
    chiamate: list[str] = []

    async def refresh() -> bool:
        chiamate.append("refresh")
        return True

    http = CanvasHttp(
        session, BASE, unwrap_backend, auth_provider=lambda: "tok", on_unauthorized=refresh
    )
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", status=401)
        mocked.post(f"{BASE}/ping", payload={"resultCode": 100, "data": {"ok": True}})
        assert await http.request("/ping") == {"ok": True}
    assert chiamate == ["refresh"]


async def test_401_due_volte_solleva_auth_error(session) -> None:
    async def refresh() -> bool:
        return True

    http = CanvasHttp(
        session, BASE, unwrap_backend, auth_provider=lambda: "tok", on_unauthorized=refresh
    )
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", status=401)
        mocked.post(f"{BASE}/ping", status=401)
        with pytest.raises(SwitchBotCanvasAuthError):
            await http.request("/ping")


async def test_401_senza_refresh_disponibile_solleva_subito(session) -> None:
    http = CanvasHttp(session, BASE, unwrap_backend, auth_provider=lambda: "tok")
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", status=401)
        with pytest.raises(SwitchBotCanvasAuthError):
            await http.request("/ping")


async def test_refresh_fallito_solleva_auth_error(session) -> None:
    async def refresh() -> bool:
        return False

    http = CanvasHttp(
        session, BASE, unwrap_backend, auth_provider=lambda: "tok", on_unauthorized=refresh
    )
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", status=401)
        with pytest.raises(SwitchBotCanvasAuthError):
            await http.request("/ping")


async def test_errore_http_generico_solleva_api_error(session) -> None:
    from custom_components.switchbot_eink.api.errors import SwitchBotCanvasApiError

    http = CanvasHttp(session, BASE, unwrap_backend)
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", status=500)
        with pytest.raises(SwitchBotCanvasApiError):
            await http.request("/ping")
