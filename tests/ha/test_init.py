"""Test di async_setup_entry: costruzione del client, coordinator, primo refresh."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.switchbot_eink.api.auth import Tokens
from custom_components.switchbot_eink.const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_TOKEN_TYPE,
    CONF_USER_ID,
    DOMAIN,
)
from custom_components.switchbot_eink.coordinator import SwitchBotEinkCoordinator

DATI = {
    CONF_REGION: "eu",
    CONF_ACCESS_TOKEN: "AT",
    CONF_REFRESH_TOKEN: "RT",
    CONF_TOKEN_TYPE: "Bearer",
    CONF_USER_ID: "user-1",
    CONF_DEVICE_ID: "DEV1",
}

PERCORSO_CLIENT = "custom_components.switchbot_eink.SwitchBotCanvasClient"
PERCORSO_PUBLISH = (
    "custom_components.switchbot_eink.coordinator.SwitchBotEinkCoordinator.async_publish"
)


@pytest.fixture
def entry():
    return MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data=dict(DATI))


def _mock_client(mock_cls) -> None:
    mock_cls.return_value.tokens = Tokens(access_token="AT", refresh_token="RT")


async def test_setup_riuscito_registra_il_coordinator(
    hass: HomeAssistant, entry
) -> None:
    entry.add_to_hass(hass)

    with patch(PERCORSO_CLIENT) as client_cls:
        _mock_client(client_cls)
        with patch(PERCORSO_PUBLISH, AsyncMock(return_value=True)):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, SwitchBotEinkCoordinator)


async def test_il_token_scaduto_avvia_il_reauth(hass: HomeAssistant, entry) -> None:
    entry.add_to_hass(hass)

    with patch(PERCORSO_CLIENT) as client_cls:
        _mock_client(client_cls)
        with patch(
            PERCORSO_PUBLISH, AsyncMock(side_effect=ConfigEntryAuthFailed("scaduto"))
        ):
            assert await hass.config_entries.async_setup(entry.entry_id) is False
            await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flussi = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"].get("source") == "reauth" for f in flussi)


async def test_un_guasto_transitorio_mette_l_entry_in_retry(
    hass: HomeAssistant, entry
) -> None:
    entry.add_to_hass(hass)

    with patch(PERCORSO_CLIENT) as client_cls:
        _mock_client(client_cls)
        with patch(PERCORSO_PUBLISH, AsyncMock(side_effect=UpdateFailed("boom"))):
            assert await hass.config_entries.async_setup(entry.entry_id) is False
            await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
