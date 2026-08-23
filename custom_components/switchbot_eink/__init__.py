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

    # DataUpdateCoordinator arma il timer periodico solo se ha almeno un
    # ascoltatore. Questo coordinator esiste per produrre un effetto (pubblicare
    # sul pannello), non per servire dati a delle entita': senza un ascoltatore
    # proprio pubblicherebbe una volta sola all'avvio e mai piu'. Le entita'
    # diagnostiche di un task futuro diventeranno ascoltatori vere, ma la
    # correttezza non deve dipendere dalla loro esistenza.
    entry.async_on_unload(coordinator.async_add_listener(lambda: None))

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_ricarica_su_cambio_opzioni))
    return True


async def _ricarica_su_cambio_opzioni(
    hass: HomeAssistant, entry: SwitchBotEinkConfigEntry
) -> None:
    """Ricarica la entry quando l'utente cambia calendari o intervallo.

    `async_update_entry` risveglia questo listener anche quando cambia solo
    `entry.data` — un token rinnovato, un nuovo id di template — non solo
    quando cambiano le opzioni. Ricaricare in quel caso sarebbe uno spreco e
    aprirebbe un ciclo: il reload pubblica, la pubblicazione ripersiste i dati,
    i dati risvegliano di nuovo questo listener. Si ricarica solo se le opzioni
    sono davvero diverse da quelle con cui il coordinator attuale e' stato
    creato.
    """
    # Il nucleo cancella `runtime_data` allo unload mentre i listener girano
    # come task differiti: getattr con default chiude la finestra teorica in
    # cui questo listener venisse eseguito dopo che la entry e' gia' scaricata.
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None:
        return
    if dict(entry.options) == coordinator.opzioni_iniziali:
        return
    _LOGGER.debug("Opzioni cambiate, ricarico la entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: SwitchBotEinkConfigEntry
) -> bool:
    """Scarica la entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
