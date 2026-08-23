"""Test del coordinator: agenda dai calendari, hash, token, errori."""
from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.switchbot_eink.api.auth import Tokens
from custom_components.switchbot_eink.api.errors import (
    SwitchBotCanvasApiError,
    SwitchBotCanvasAuthError,
)
from custom_components.switchbot_eink.api.models import TemplateSummary
from custom_components.switchbot_eink.const import (
    CONF_ACCESS_TOKEN,
    CONF_CALENDARS,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_TEMPLATE_ID,
    CONF_TOKEN_TYPE,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    MIN_PUBLISH_INTERVAL,
)
from custom_components.switchbot_eink.coordinator import SwitchBotEinkCoordinator

TOKENS = Tokens(access_token="AT", refresh_token="RT", token_type="Bearer")

DATI_BASE = {
    CONF_DEVICE_ID: "DEV1",
    CONF_ACCESS_TOKEN: "AT",
    CONF_REFRESH_TOKEN: "RT",
    CONF_TOKEN_TYPE: "Bearer",
}


def _registra_get_events(hass: HomeAssistant, risposta: dict) -> None:
    async def handler(call):
        return risposta

    hass.services.async_register(
        "calendar", "get_events", handler, supports_response=SupportsResponse.ONLY
    )


async def _con_un_evento(hass: HomeAssistant, entity_id: str = "calendar.lavoro") -> None:
    """Registra un calendario con un evento oggi, ancorato ad ADESSO.

    Ancorato a un offset da `dt_util.now()` invece che a un'ora assoluta: un
    orario fisso sparirebbe o resterebbe a seconda di quando gira il test,
    perche' l'agenda filtra gli eventi gia' conclusi (vedi tests/layout/test_agenda.py).
    """
    hass.states.async_set(entity_id, "on", {"friendly_name": "Lavoro"})
    adesso = dt_util.now()
    inizio = adesso + timedelta(minutes=30)
    fine = inizio + timedelta(hours=1)
    _registra_get_events(
        hass,
        {
            entity_id: {
                "events": [
                    {
                        "start": inizio.isoformat(),
                        "end": fine.isoformat(),
                        "summary": "Riunione",
                    }
                ]
            }
        },
    )


def _testi_delle_card(template) -> set:
    return {
        json.loads(c["extra"])["content"].get("text") for c in template.components
    }


@pytest.fixture
def entry():
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={**DATI_BASE, CONF_TEMPLATE_ID: 77},
        options={CONF_CALENDARS: ["calendar.lavoro"]},
    )


@pytest.fixture
def client():
    mock = MagicMock()
    mock.list_templates = AsyncMock(
        return_value=[TemplateSummary(template_id=77, name="Agenda", page_slot="home")]
    )
    mock.create_template = AsyncMock(return_value=77)
    mock.update_template = AsyncMock()
    mock.release = AsyncMock()
    mock.tokens = TOKENS
    return mock


async def test_la_prima_pubblicazione_aggiorna_e_rilascia(
    hass: HomeAssistant, entry, client
) -> None:
    entry.add_to_hass(hass)
    await _con_un_evento(hass)
    coordinator = SwitchBotEinkCoordinator(hass, entry, client)

    assert await coordinator.async_publish() is True
    client.update_template.assert_awaited_once()
    client.release.assert_awaited_once_with("DEV1")


async def test_non_ripubblica_se_l_hash_non_cambia(
    hass: HomeAssistant, entry, client
) -> None:
    entry.add_to_hass(hass)
    await _con_un_evento(hass)
    coordinator = SwitchBotEinkCoordinator(hass, entry, client)

    await coordinator.async_publish()
    client.update_template.reset_mock()
    client.release.reset_mock()

    assert await coordinator.async_publish() is False
    client.update_template.assert_not_awaited()
    client.release.assert_not_awaited()


async def test_force_ripubblica_anche_a_hash_invariato(
    hass: HomeAssistant, entry, client
) -> None:
    entry.add_to_hass(hass)
    await _con_un_evento(hass)
    coordinator = SwitchBotEinkCoordinator(hass, entry, client)

    await coordinator.async_publish()
    client.release.reset_mock()

    assert await coordinator.async_publish(force=True) is True
    client.release.assert_awaited_once()


async def test_crea_il_template_se_lo_slot_e_vuoto(hass: HomeAssistant, client) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data=dict(DATI_BASE))
    entry.add_to_hass(hass)
    client.list_templates = AsyncMock(return_value=[])

    coordinator = SwitchBotEinkCoordinator(hass, entry, client)
    assert await coordinator.async_publish() is True

    client.create_template.assert_awaited_once()
    client.update_template.assert_not_awaited()


async def test_nessun_calendario_scelto_produce_l_agenda_vuota_senza_eccezioni(
    hass: HomeAssistant, client
) -> None:
    """Stato iniziale dopo l'installazione: nessuna eccezione, agenda vuota."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={**DATI_BASE, CONF_TEMPLATE_ID: 77},
    )
    entry.add_to_hass(hass)
    coordinator = SwitchBotEinkCoordinator(hass, entry, client)

    assert await coordinator.async_publish() is True

    template = client.update_template.await_args.args[0]
    assert any(
        testo and "Nessun evento nei prossimi 3 giorni" in testo
        for testo in _testi_delle_card(template)
    )


async def test_i_marcatori_restano_anche_se_un_calendario_non_ha_eventi(
    hass: HomeAssistant, client
) -> None:
    """`calendars` deve arrivare dalle opzioni, non dedotto dagli eventi presenti.

    Due calendari scelti, uno solo con un evento oggi: il marcatore deve
    comunque comparire. Se `calendars` non venisse passato a
    `build_agenda_page`, i nomi verrebbero dedotti dai soli eventi effettivi
    (un solo calendario) e i marcatori sparirebbero del tutto.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={**DATI_BASE, CONF_TEMPLATE_ID: 77},
        options={CONF_CALENDARS: ["calendar.lavoro", "calendar.personale"]},
    )
    entry.add_to_hass(hass)
    hass.states.async_set("calendar.personale", "on", {"friendly_name": "Personale"})
    await _con_un_evento(hass)

    coordinator = SwitchBotEinkCoordinator(hass, entry, client)
    assert await coordinator.async_publish() is True

    template = client.update_template.await_args.args[0]
    assert "L" in _testi_delle_card(template)


async def test_auth_ok_diventa_falso_e_scatena_il_reauth(
    hass: HomeAssistant, entry, client
) -> None:
    entry.add_to_hass(hass)
    await _con_un_evento(hass)
    client.update_template = AsyncMock(side_effect=SwitchBotCanvasAuthError("scaduto"))
    coordinator = SwitchBotEinkCoordinator(hass, entry, client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator.async_publish()

    assert coordinator.auth_ok is False


async def test_errore_transitorio_diventa_updatefailed(
    hass: HomeAssistant, entry, client
) -> None:
    entry.add_to_hass(hass)
    await _con_un_evento(hass)
    client.update_template = AsyncMock(side_effect=SwitchBotCanvasApiError(500, "boom"))
    coordinator = SwitchBotEinkCoordinator(hass, entry, client)

    with pytest.raises(UpdateFailed):
        await coordinator.async_publish()


async def test_l_intervallo_minimo_e_imposto_anche_se_le_opzioni_lo_violano(
    hass: HomeAssistant, client
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data=dict(DATI_BASE),
        options={CONF_UPDATE_INTERVAL: 10},
    )
    entry.add_to_hass(hass)

    coordinator = SwitchBotEinkCoordinator(hass, entry, client)

    assert coordinator.update_interval == timedelta(seconds=MIN_PUBLISH_INTERVAL)


async def test_i_token_rinnovati_vengono_ripersistiti(
    hass: HomeAssistant, entry, client
) -> None:
    entry.add_to_hass(hass)
    await _con_un_evento(hass)
    client.tokens = Tokens(access_token="NUOVO", refresh_token="RT2", token_type="Bearer")
    coordinator = SwitchBotEinkCoordinator(hass, entry, client)

    await coordinator.async_publish()

    assert entry.data[CONF_ACCESS_TOKEN] == "NUOVO"
    assert entry.data[CONF_REFRESH_TOKEN] == "RT2"
