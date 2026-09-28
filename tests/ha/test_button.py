"""Test del pulsante che ripubblica l'agenda di un pannello."""
from __future__ import annotations

import pytest
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.switchbot_eink.api.errors import SwitchBotCanvasApiError
from custom_components.switchbot_eink.const import DOMAIN
from tests.ha.test_services import _new_client_mock, _setup, _setup_two

# Come per le entita' diagnostiche: nome del device + traduzione inglese.
BUTTON_ID = "button.cucina_refresh_agenda"
BUTTON_ID_2 = "button.salotto_refresh_agenda"


@pytest.fixture
def client_mock():
    return _new_client_mock()


@pytest.fixture
def client_mock_2():
    return _new_client_mock()


async def _premi(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    await hass.async_block_till_done()


async def test_il_pulsante_e_collegato_al_device_del_pannello(
    hass: HomeAssistant, client_mock
) -> None:
    entry = await _setup(hass, client_mock)

    voce = er.async_get(hass).async_get(BUTTON_ID)
    assert voce is not None
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, "DEV1"), entry.entry_id
    )
    assert device is not None
    assert voce.device_id == device.id
    # Un comando, non un'informazione: sta fra i controlli, non in diagnostica.
    assert voce.entity_category is None


async def test_premere_ripubblica_anche_senza_modifiche(
    hass: HomeAssistant, client_mock, freezer
) -> None:
    """E' la ragione del pulsante: dopo il setup l'agenda e' invariata, e senza
    forzare l'impronta impedirebbe la ripubblicazione."""
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup(hass, client_mock)
    client_mock.release.reset_mock()

    freezer.tick(61)
    await _premi(hass, BUTTON_ID)

    client_mock.release.assert_awaited_once_with("DEV1")


async def test_premere_ripubblica_solo_il_proprio_pannello(
    hass: HomeAssistant, client_mock, client_mock_2, freezer
) -> None:
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup_two(hass, client_mock, client_mock_2)
    client_mock.release.reset_mock()
    client_mock_2.release.reset_mock()

    freezer.tick(61)
    await _premi(hass, BUTTON_ID_2)

    client_mock_2.release.assert_awaited_once_with("DEV2")
    client_mock.release.assert_not_awaited()


async def test_premere_due_volte_di_fila_rispetta_lintervallo_minimo(
    hass: HomeAssistant, client_mock, freezer
) -> None:
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup(hass, client_mock)
    client_mock.release.reset_mock()

    freezer.tick(61)
    await _premi(hass, BUTTON_ID)
    freezer.tick(5)
    await _premi(hass, BUTTON_ID)

    client_mock.release.assert_awaited_once()


async def test_una_pubblicazione_fallita_si_vede_nellinterfaccia(
    hass: HomeAssistant, client_mock, freezer
) -> None:
    """Chi preme deve sapere che non e' successo niente, e perche'."""
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup(hass, client_mock)

    freezer.tick(61)
    client_mock.release.side_effect = SwitchBotCanvasApiError(500, "boom")

    with pytest.raises(HomeAssistantError, match="Cucina"):
        await _premi(hass, BUTTON_ID)
