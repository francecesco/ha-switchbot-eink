"""Test del servizio refresh e delle entità diagnostiche."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.switchbot_eink.api.models import TemplateSummary
from custom_components.switchbot_eink.const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_TEMPLATE_ID,
    CONF_TOKEN_TYPE,
    CONF_USER_ID,
    DOMAIN,
    SERVICE_REFRESH,
)

DATA = {
    CONF_REGION: "eu",
    CONF_ACCESS_TOKEN: "AT",
    CONF_REFRESH_TOKEN: "RT",
    CONF_TOKEN_TYPE: "Bearer",
    CONF_USER_ID: "user-1",
    CONF_DEVICE_ID: "DEV1",
    CONF_DEVICE_NAME: "Cucina",
    CONF_TEMPLATE_ID: 77,
}


@pytest.fixture
def client_mock():
    mock = MagicMock()
    mock.tokens = MagicMock(access_token="AT", refresh_token="RT", token_type="Bearer")
    mock.list_templates = AsyncMock(
        return_value=[TemplateSummary(template_id=77, name="Casa", page_slot="custom1")]
    )
    mock.update_template = AsyncMock()
    mock.release = AsyncMock()
    return mock


async def _setup(hass: HomeAssistant, client_mock) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data=DATA)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_eink.SwitchBotCanvasClient", return_value=client_mock
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_il_servizio_refresh_e_registrato(hass: HomeAssistant, client_mock) -> None:
    await _setup(hass, client_mock)

    assert hass.services.has_service(DOMAIN, SERVICE_REFRESH)


async def test_refresh_ripubblica_anche_senza_modifiche(
    hass: HomeAssistant, client_mock, freezer
) -> None:
    """Il servizio deve chiamare `async_publish(force=True)`: senza `force`
    l'hash invariato dall'ultima pubblicazione (avvenuta al setup) bloccherebbe
    la riscrittura e `release` non verrebbe mai chiamato di nuovo."""
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup(hass, client_mock)
    client_mock.release.reset_mock()

    freezer.tick(61)  # oltre il vincolo minimo fra due pubblicazioni
    await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)
    await hass.async_block_till_done()

    client_mock.release.assert_awaited()


async def test_refresh_non_solleva_se_il_minimo_non_e_rispettato(
    hass: HomeAssistant, client_mock, freezer
) -> None:
    """`force` scavalca il confronto dell'hash ma non il vincolo dei 60 secondi
    minimi fra due pubblicazioni: se il servizio viene chiamato subito dopo il
    setup, `async_publish` ritorna False e il servizio non deve sollevare."""
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup(hass, client_mock)
    client_mock.release.reset_mock()

    # Nessun avanzamento dell'orologio: siamo ancora dentro il minuto minimo.
    await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)
    await hass.async_block_till_done()

    client_mock.release.assert_not_awaited()


async def test_unload_dell_ultima_entry_rimuove_il_servizio(
    hass: HomeAssistant, client_mock
) -> None:
    entry = await _setup(hass, client_mock)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert not hass.services.has_service(DOMAIN, SERVICE_REFRESH)


async def test_il_sensore_di_ultima_pubblicazione_esiste(
    hass: HomeAssistant, client_mock
) -> None:
    await _setup(hass, client_mock)

    stato = hass.states.get("sensor.cucina_ultima_pubblicazione")
    assert stato is not None
    assert stato.state not in (None, "unknown", "unavailable")


async def test_il_sensore_si_aggiorna_dopo_il_refresh(
    hass: HomeAssistant, client_mock, freezer
) -> None:
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup(hass, client_mock)

    stato_prima = hass.states.get("sensor.cucina_ultima_pubblicazione")
    assert stato_prima is not None

    freezer.tick(61)
    await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)
    await hass.async_block_till_done()

    stato_dopo = hass.states.get("sensor.cucina_ultima_pubblicazione")
    assert dt_util.parse_datetime(stato_dopo.state) > dt_util.parse_datetime(
        stato_prima.state
    )


async def test_il_binary_sensor_di_autenticazione_e_a_posto(
    hass: HomeAssistant, client_mock
) -> None:
    await _setup(hass, client_mock)

    stato = hass.states.get("binary_sensor.cucina_autenticazione")
    assert stato is not None
    assert stato.state == "off", "off significa nessun problema per la classe PROBLEM"


async def test_le_entita_diagnostiche_sono_collegate_al_device_del_pannello(
    hass: HomeAssistant, client_mock
) -> None:
    await _setup(hass, client_mock)

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    device = device_registry.async_get_device(identifiers={(DOMAIN, "DEV1")})
    assert device is not None

    for entity_id in (
        "sensor.cucina_ultima_pubblicazione",
        "binary_sensor.cucina_autenticazione",
    ):
        voce = entity_registry.async_get(entity_id)
        assert voce is not None
        assert voce.device_id == device.id
