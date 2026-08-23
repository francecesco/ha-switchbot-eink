"""Integrazione SwitchBot E-Ink Home Dashboard."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

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


# L'integrazione si configura solo dall'interfaccia. Senza questo, da quando
# esiste `async_setup` un blocco `switchbot_eink:` in configuration.yaml verrebbe
# accettato in silenzio: chi lo scrivesse aspetterebbe un effetto che non arriva,
# senza un avviso da nessuna parte.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Registra i servizi del dominio.

    Un servizio va registrato qui, non in `async_setup_entry`: se vivesse li'
    sparirebbe per la finestra di un reload (unload seguito da un nuovo
    setup della stessa entry), e un'automazione che chiamasse `refresh`
    proprio in quella finestra fallirebbe con "servizio sconosciuto".
    `async_setup` viene invocato una volta sola per l'intera vita di questa
    istanza di Home Assistant, indipendentemente da quante entry esistono o
    da quante volte vengono ricaricate: il servizio non va mai rimosso.
    """
    _register_services(hass)
    return True


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
    return True


def _register_services(hass: HomeAssistant) -> None:
    """Registra il servizio `refresh`. Chiamato da `async_setup`: non va mai rimosso."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    def _coordinatori_caricati() -> list[SwitchBotEinkCoordinator]:
        return [
            entry.runtime_data
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]

    async def handle_refresh(call: ServiceCall) -> None:
        coordinatori = _coordinatori_caricati()
        if not coordinatori:
            raise HomeAssistantError(
                "Nessun pannello SwitchBot E-Ink caricato: nulla da aggiornare"
            )

        # Il fan-out non si ferma al primo pannello guasto: un pannello rotto
        # non deve impedire agli altri di aggiornarsi. Gli errori si
        # accumulano e si sollevano tutti insieme alla fine.
        errori: list[Exception] = []
        for coordinator in coordinatori:
            try:
                await coordinator.async_forza_pubblicazione()
            except HomeAssistantError as err:
                errori.append(err)

        if errori:
            # Ogni errore nomina gia' il proprio pannello e porta la causa: qui
            # basta cucirli insieme. Il conteggio serve solo quando i pannelli
            # sono piu' di uno, altrimenti e' rumore ("1 pannello su 1").
            testa = (
                f"{len(errori)} pannelli su {len(coordinatori)} non aggiornati. "
                if len(coordinatori) > 1
                else ""
            )
            raise HomeAssistantError(
                testa + " ".join(str(err) for err in errori)
            ) from errori[0]

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
    """Scarica la entry.

    Il servizio `refresh`, registrato a livello di dominio in `async_setup`,
    non viene toccato: non e' legato al ciclo di vita di una singola entry, e
    un servizio registrato a livello di dominio non va rimosso.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
