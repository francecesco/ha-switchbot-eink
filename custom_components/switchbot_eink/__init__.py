"""Integrazione SwitchBot E-Ink Home Dashboard."""
from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.auth import Tokens
from .api.client import SwitchBotCanvasClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_TOKEN_TYPE,
    CONF_USER_ID,
)
from .coordinator import SwitchBotEinkConfigEntry, SwitchBotEinkCoordinator

_LOGGER = logging.getLogger(__name__)

# Nessuna entita' propria ancora: il coordinator basta a pubblicare l'agenda.
PLATFORMS: list[Platform] = []


async def async_setup_entry(
    hass: HomeAssistant, entry: SwitchBotEinkConfigEntry
) -> bool:
    """Avvia il client e il coordinator, che genera l'agenda dai calendari."""
    tokens = Tokens(
        access_token=entry.data[CONF_ACCESS_TOKEN],
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        token_type=entry.data.get(CONF_TOKEN_TYPE, "Bearer"),
    )
    client = SwitchBotCanvasClient(
        async_get_clientsession(hass),
        entry.data[CONF_REGION],
        tokens,
        entry.data[CONF_USER_ID],
    )

    coordinator = SwitchBotEinkCoordinator(hass, entry, client)

    # Converte i guasti in ConfigEntryAuthFailed / ConfigEntryNotReady: e' il
    # coordinator stesso a tradurre gli errori dell'API (vedi async_publish),
    # DataUpdateCoordinator si occupa del resto — reauth per il primo, nuovo
    # tentativo di setup per il secondo.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SwitchBotEinkConfigEntry
) -> bool:
    """Scarica la entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
