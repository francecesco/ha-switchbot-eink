"""Integrazione SwitchBot E-Ink Home Dashboard."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.auth import Tokens
from .api.client import SwitchBotCanvasClient
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_TOKEN_TYPE,
    CONF_USER_ID,
    DOMAIN,
    SERVICE_REFRESH,
)
from .coordinator import SwitchBotEinkConfigEntry, SwitchBotEinkCoordinator

_LOGGER = logging.getLogger(__name__)

# Le entita' diagnostiche di questo task: oltre a esporre stato, sono
# ascoltatori veri del coordinator (vedi il commento sull'ascoltatore finto
# piu' sotto).
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


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
    # diagnostiche aggiunte con questo task sono ascoltatori veri, ma la
    # correttezza non deve dipendere dalla loro esistenza (ne' da come sono
    # implementate): l'ascoltatore finto resta indipendente da loro.
    entry.async_on_unload(coordinator.async_add_listener(lambda: None))

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_ricarica_su_cambio_opzioni))
    _register_services(hass)
    return True


def _register_services(hass: HomeAssistant) -> None:
    """Registra il servizio `refresh` una sola volta, alla prima entry configurata."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    def _coordinators() -> list[SwitchBotEinkCoordinator]:
        return [
            entry.runtime_data
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]

    async def handle_refresh(call: ServiceCall) -> None:
        for coordinator in _coordinators():
            await coordinator.async_publish(force=True)
            # `async_publish` chiamato cosi', fuori dal ciclo di
            # `_async_refresh`, non passa mai da `async_update_listeners`:
            # senza questa chiamata esplicita le entita' diagnostiche
            # resterebbero ferme al valore del ciclo periodico precedente
            # fino al prossimo giro del timer.
            coordinator.async_update_listeners()

    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH, handle_refresh, schema=vol.Schema({})
    )


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
    """Scarica la entry e, se era l'ultima, il servizio `refresh` con lei."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # A questo punto il nucleo non ha ancora marcato `entry` come
        # scaricata (lo fa dopo che questa funzione ritorna): va esclusa
        # esplicitamente dal conteggio delle entry ancora caricate.
        altre_caricate = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED
        ]
        if not altre_caricate:
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
    return unload_ok
