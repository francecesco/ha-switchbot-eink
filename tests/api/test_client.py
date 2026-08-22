"""Test dei modelli e della facciata del client."""
from __future__ import annotations

import asyncio

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import mock_aiohttp_client

from custom_components.switchbot_eink.api.auth import Tokens
from custom_components.switchbot_eink.api.client import SwitchBotCanvasClient
from custom_components.switchbot_eink.api.models import (
    Template,
    page_slot_to_sort_order,
    page_slot_to_template_type,
)

BASE = "https://wonderlabs.eu.api.switchbot.net/productbiz"
BASE_US = "https://wonderlabs.us.api.switchbot.net/productbiz"
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


async def test_list_eink_devices_filtra_per_tipo_e_condivisione(aioclient, client) -> None:
    aioclient.post(
        f"{BASE}/device/v1/manage/getDeviceList",
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
