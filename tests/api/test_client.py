"""Test dei modelli e della facciata del client."""
from __future__ import annotations

import asyncio

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
    mock_aiohttp_client,
)
from yarl import URL

from custom_components.switchbot_eink.api.auth import Tokens
from custom_components.switchbot_eink.api.client import SwitchBotCanvasClient
from custom_components.switchbot_eink.api.errors import SwitchBotCanvasAuthError
from custom_components.switchbot_eink.api.models import (
    Template,
    page_slot_to_sort_order,
    page_slot_to_template_type,
    sort_order_to_page_slot,
)
from tests.api.helpers import response_sequence

BASE = "https://wonderlabs.eu.api.switchbot.net/productbiz"
BASE_US = "https://wonderlabs.us.api.switchbot.net/productbiz"
DEVICE_BASE = "https://wonderlabs.eu.api.switchbot.net"
ACCOUNT = "https://account.api.switchbot.net"
TOKENS = Tokens(access_token="AT", refresh_token="RT", token_type="Bearer")


@pytest.fixture
async def aioclient():
    with mock_aiohttp_client() as mocker:
        yield mocker


@pytest.fixture
async def session(aioclient):
    sess = aioclient.create_session(asyncio.get_running_loop())
    yield sess
    await sess.close()


@pytest.fixture
def client(session):
    return SwitchBotCanvasClient(session, "eu", TOKENS, user_id="user-1")


def test_slot_home_mappa_su_template_type_1() -> None:
    assert page_slot_to_template_type("home") == 1
    assert page_slot_to_sort_order("home") == 1


def test_slot_custom_mappa_su_template_type_0() -> None:
    assert page_slot_to_template_type("custom3") == 0
    assert page_slot_to_sort_order("custom3") == 3


def test_slot_sconosciuto_ha_sort_order_zero() -> None:
    assert page_slot_to_sort_order("unassigned") == 0


def test_slot_dedotto_dalla_home() -> None:
    assert sort_order_to_page_slot(1, 1) == "home"


def test_slot_dedotto_dalle_pagine_custom() -> None:
    assert sort_order_to_page_slot(1, 0) == "custom1"
    assert sort_order_to_page_slot(4, 0) == "custom4"


def test_slot_dedotto_fuori_intervallo_e_unassigned() -> None:
    assert sort_order_to_page_slot(0, 0) == "unassigned"
    assert sort_order_to_page_slot(9, 0) == "unassigned"


async def test_list_templates_deduce_lo_slot_dai_campi_reali(aioclient, client) -> None:
    """La risposta non contiene pageSlot: lo slot va dedotto da sortOrder e templateType.

    Questo payload e' copiato da una risposta reale del backend. La home e
    custom1 hanno entrambe sortOrder 1: guardare solo quello le confonderebbe.
    """
    aioclient.post(
        f"{BASE}/web/v1/user/templates/list",
        json={
            "resultCode": 100,
            "data": {
                "total": 3,
                "items": [
                    {"templateId": 1105, "name": "Home template", "sortOrder": 1,
                     "templateType": 1, "deviceID": "A", "enabled": True},
                    {"templateId": 580, "name": "Untitled template", "sortOrder": 1,
                     "templateType": 0, "deviceID": "A", "enabled": True},
                    {"templateId": 1316, "name": "Untitled template", "sortOrder": 2,
                     "templateType": 0, "deviceID": "A", "enabled": True},
                ],
            },
        },
    )

    summaries = await client.list_templates("A")

    assert [s.page_slot for s in summaries] == ["home", "custom1", "custom2"]
    assert [s.template_id for s in summaries] == [1105, 580, 1316]
    assert summaries[0].template_type == 1


async def test_list_templates_non_cerca_una_chiave_page_slot(aioclient, client) -> None:
    """Regressione: cercare `pageSlot` dava `unassigned` a tutto e faceva fallire il filtro."""
    aioclient.post(
        f"{BASE}/web/v1/user/templates/list",
        json={
            "resultCode": 100,
            "data": {"items": [
                {"templateId": 7, "name": "x", "sortOrder": 3, "templateType": 0}
            ]},
        },
    )

    summaries = await client.list_templates("A")

    assert summaries[0].page_slot == "custom3"


async def test_list_eink_devices_filtra_per_tipo_e_condivisione(aioclient, client) -> None:
    aioclient.post(
        f"{DEVICE_BASE}/device/v1/manage/getDeviceList",
        json={
            "resultCode": 100,
            "data": [
                {"deviceID": "A", "deviceName": "Pannello", "deviceType": "W1070000",
                 "isShare": False},
                {"deviceID": "B", "deviceName": "Condiviso", "deviceType": "W1070000",
                 "isShare": True},
                {"deviceID": "C", "deviceName": "Meter", "deviceType": "WoMeter",
                 "isShare": False},
            ],
        },
    )

    devices = await client.list_eink_devices()

    assert [d.device_id for d in devices] == ["A"]


async def test_la_lista_dispositivi_non_passa_da_productbiz(aioclient, client) -> None:
    """Con /productbiz la rotta non esiste e API Gateway risponde 403 parlando di firme AWS."""
    aioclient.post(
        f"{DEVICE_BASE}/device/v1/manage/getDeviceList",
        json={"resultCode": 100, "data": []},
    )

    await client.list_devices()
    _method, url, _body, _headers = aioclient.mock_calls[0]

    assert "/productbiz" not in str(url)
    assert str(url).endswith("/device/v1/manage/getDeviceList")


async def test_create_template_invia_sort_order_e_restituisce_id(aioclient, client) -> None:
    aioclient.post(
        f"{BASE}/web/v1/user/templates/create",
        json={"resultCode": 100, "data": {"templateId": 77}},
    )
    template = Template(
        template_id=None,
        name="Casa",
        page_slot="custom1",
        device_id="A",
        components=[{"id": "1", "type": "text", "name": "t", "css": "{}", "extra": "{}"}],
    )

    template_id = await client.create_template(template)
    _method, _url, body, _headers = aioclient.mock_calls[0]

    assert body["sortOrder"] == 1
    assert body["templateType"] == 0
    assert body["enabled"] is True
    assert body["deviceID"] == "A"
    assert body["components"][0]["css"] == "{}"
    assert template_id == 77


async def test_update_template_include_sort_order_per_le_pagine_custom(
    aioclient, client
) -> None:
    aioclient.post(f"{BASE}/web/v1/user/templates/update", json={"resultCode": 100, "data": None})
    template = Template(
        template_id=77, name="Casa", page_slot="custom2", device_id="A", components=[]
    )

    await client.update_template(template)
    _method, _url, body, _headers = aioclient.mock_calls[0]

    assert body["templateId"] == 77
    assert body["sortOrder"] == 2


async def test_update_template_omette_sort_order_per_la_home(aioclient, client) -> None:
    aioclient.post(f"{BASE}/web/v1/user/templates/update", json={"resultCode": 100, "data": None})
    template = Template(
        template_id=77, name="Home", page_slot="home", device_id="A", components=[]
    )

    await client.update_template(template)
    _method, _url, body, _headers = aioclient.mock_calls[0]

    assert "sortOrder" not in body


async def test_release_invia_solo_il_device_id(aioclient, client) -> None:
    aioclient.post(f"{BASE}/web/v1/user/templates/release", json={"resultCode": 100, "data": None})

    await client.release("A")
    _method, _url, body, _headers = aioclient.mock_calls[0]

    assert body == {"deviceID": "A"}


async def test_header_authorization_senza_bearer_in_eu(aioclient, client) -> None:
    aioclient.post(f"{BASE}/web/v1/user/templates/release", json={"resultCode": 100, "data": None})

    await client.release("A")
    _method, _url, _body, headers = aioclient.mock_calls[0]

    assert headers["Authorization"] == "AT"


async def test_header_authorization_con_bearer_in_us(aioclient, session) -> None:
    aioclient.post(
        f"{BASE_US}/web/v1/user/templates/release", json={"resultCode": 100, "data": None}
    )
    client_us = SwitchBotCanvasClient(session, "us", TOKENS, user_id="user-1")

    await client_us.release("A")
    _method, _url, _body, headers = aioclient.mock_calls[0]

    assert headers["Authorization"] == "Bearer AT"


async def test_401_rinnova_il_token_e_ripete_la_chiamata(aioclient, session) -> None:
    """Su 401 il client rinnova l'access token da solo e ripete la richiesta."""
    release_url = f"{BASE}/web/v1/user/templates/release"
    aioclient.post(
        release_url,
        side_effect=response_sequence(
            AiohttpClientMockResponse("post", URL(release_url), status=401),
            AiohttpClientMockResponse(
                "post", URL(release_url), status=200, json={"resultCode": 100, "data": None}
            ),
        ),
    )
    aioclient.post(
        f"{ACCOUNT}/account/api/v1/user/token/refresh",
        json={"statusCode": 100, "body": {"access_token": "AT2", "token_type": "Bearer"}},
    )
    client = SwitchBotCanvasClient(session, "eu", TOKENS, user_id="user-1")

    await client.release("A")

    assert client.tokens.access_token == "AT2", (
        "i token aggiornati devono restare leggibili, il chiamante deve ripersistirli"
    )
    assert client.tokens.refresh_token == "RT", "il refresh token non cambia"

    _method, _url, _body, headers = aioclient.mock_calls[-1]
    assert headers["Authorization"] == "AT2", "la ripetizione usa il token nuovo"


async def test_401_con_refresh_fallito_solleva_auth_error(aioclient, session) -> None:
    """Se il rinnovo non riesce, l'errore emerge e i vecchi token restano intatti."""
    aioclient.post(f"{BASE}/web/v1/user/templates/release", status=401)
    aioclient.post(
        f"{ACCOUNT}/account/api/v1/user/token/refresh",
        json={"statusCode": 160, "message": "refresh token revocato"},
    )
    client = SwitchBotCanvasClient(session, "eu", TOKENS, user_id="user-1")

    with pytest.raises(SwitchBotCanvasAuthError):
        await client.release("A")

    assert client.tokens.access_token == "AT", "i token non vengono sporcati da un rinnovo fallito"


async def test_update_template_omette_sort_order_per_uno_slot_sconosciuto(
    aioclient, client
) -> None:
    """Uno slot non riconosciuto ha sortOrder 0, e lo zero non va sul filo."""
    aioclient.post(f"{BASE}/web/v1/user/templates/update", json={"resultCode": 100, "data": None})
    template = Template(
        template_id=77, name="Bozza", page_slot="unassigned", device_id="A", components=[]
    )

    assert template.template_type == 0, "presupposto del test: non è la home"
    assert template.sort_order == 0, "presupposto del test: slot non riconosciuto"

    await client.update_template(template)
    _method, _url, body, _headers = aioclient.mock_calls[0]

    assert "sortOrder" not in body
