"""Test del servizio refresh e delle entità diagnostiche."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.switchbot_eink.api.errors import (
    SwitchBotCanvasApiError,
    SwitchBotCanvasAuthError,
)
from custom_components.switchbot_eink.api.models import TemplateSummary
from custom_components.switchbot_eink.const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_TEMPLATE_ID,
    CONF_TOKEN_TYPE,
    CONF_UPDATE_INTERVAL,
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

DATA_2 = {
    **DATA,
    CONF_DEVICE_ID: "DEV2",
    CONF_DEVICE_NAME: "Salotto",
}

# Con `has_entity_name = True` e naming guidato da `translation_key`, l'id
# della entità si compone dal nome del device e dalla traduzione INGLESE (la
# lingua di default dell'ambiente di test), non dalla chiave usata nel
# codice né dal testo italiano di `strings.json`.
SENSOR_ID = "sensor.cucina_last_published"
BINARY_SENSOR_ID = "binary_sensor.cucina_authentication"
SENSOR_ID_2 = "sensor.salotto_last_published"
BINARY_SENSOR_ID_2 = "binary_sensor.salotto_authentication"


def _new_client_mock():
    mock = MagicMock()
    mock.tokens = MagicMock(access_token="AT", refresh_token="RT", token_type="Bearer")
    mock.list_templates = AsyncMock(
        return_value=[TemplateSummary(template_id=77, name="Casa", page_slot="custom1")]
    )
    mock.update_template = AsyncMock()
    mock.release = AsyncMock()
    return mock


@pytest.fixture
def client_mock():
    return _new_client_mock()


@pytest.fixture
def client_mock_2():
    return _new_client_mock()


async def _setup(hass: HomeAssistant, client_mock) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data=DATA)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_eink.SwitchBotCanvasClient", return_value=client_mock
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def _setup_two(
    hass: HomeAssistant, client_mock, client_mock_2
) -> tuple[MockConfigEntry, MockConfigEntry]:
    """Aggiunge due entry e ne avvia il setup con un'unica chiamata.

    Il dominio non e' ancora impostato la prima volta che viene chiamato
    `hass.config_entries.async_setup`: il nucleo, per farlo, invoca
    `async_setup_component`, che a sua volta avvia il setup di *tutte* le
    entry del dominio gia' aggiunte a `hass` (non solo quella richiesta).
    Chiamare `async_setup` una seconda volta sulla seconda entry fallirebbe,
    perche' a quel punto e' gia' `LOADED`.
    """
    entry1 = MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data=DATA)
    entry2 = MockConfigEntry(domain=DOMAIN, unique_id="DEV2", data=DATA_2)
    entry1.add_to_hass(hass)
    entry2.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_eink.SwitchBotCanvasClient",
        side_effect=[client_mock, client_mock_2],
    ):
        assert await hass.config_entries.async_setup(entry1.entry_id)
        await hass.async_block_till_done()

    assert entry2.state is ConfigEntryState.LOADED
    return entry1, entry2


# ---- registrazione del servizio a livello di dominio -----------------------


async def test_il_servizio_e_registrato_da_async_setup_senza_entry(
    hass: HomeAssistant,
) -> None:
    """Il servizio vive a livello di dominio: deve esistere anche senza
    nessuna entry configurata, perché `async_setup` (non `async_setup_entry`)
    lo registra."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_REFRESH)


async def test_il_servizio_solleva_se_non_ci_sono_pannelli_caricati(
    hass: HomeAssistant,
) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)


async def test_il_servizio_e_registrato_una_volta_sola_con_due_pannelli(
    hass: HomeAssistant, client_mock, client_mock_2
) -> None:
    """`async_setup` (che registra il servizio) viene chiamato dal nucleo una
    volta sola per l'intera vita di questa istanza, indipendentemente da
    quante entry esistono: la guardia in `_register_services` resta comunque
    come seconda linea di difesa, verificata qui direttamente."""
    from custom_components.switchbot_eink import _register_services

    await _setup_two(hass, client_mock, client_mock_2)

    prima = hass.services.async_services_for_domain(DOMAIN)[SERVICE_REFRESH]
    _register_services(hass)
    dopo = hass.services.async_services_for_domain(DOMAIN)[SERVICE_REFRESH]

    assert prima is dopo, "una seconda registrazione ha sostituito il servizio"


async def test_scaricare_un_pannello_lascia_il_servizio_per_l_altro(
    hass: HomeAssistant, client_mock, client_mock_2, freezer
) -> None:
    freezer.move_to("2026-08-23T12:00:00+00:00")
    entry1, entry2 = await _setup_two(hass, client_mock, client_mock_2)

    assert await hass.config_entries.async_unload(entry1.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, SERVICE_REFRESH)

    client_mock.release.reset_mock()
    client_mock_2.release.reset_mock()
    freezer.tick(61)

    await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)
    await hass.async_block_till_done()

    client_mock_2.release.assert_awaited()
    client_mock.release.assert_not_awaited()


# ---- comportamento del servizio refresh -------------------------------


async def test_refresh_ripubblica_anche_senza_modifiche(
    hass: HomeAssistant, client_mock, freezer
) -> None:
    """Il servizio deve forzare la ripubblicazione: senza `force` l'hash
    invariato dall'ultima pubblicazione (avvenuta al setup) bloccherebbe la
    riscrittura e `release` non verrebbe mai chiamato di nuovo."""
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
    setup, la pubblicazione viene rifiutata dal vincolo e il servizio non deve
    sollevare."""
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup(hass, client_mock)
    client_mock.release.reset_mock()

    # Nessun avanzamento dell'orologio: siamo ancora dentro il minuto minimo.
    await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)
    await hass.async_block_till_done()

    client_mock.release.assert_not_awaited()


async def test_refresh_avvia_il_reauth_con_token_scaduto(
    hass: HomeAssistant, client_mock, freezer
) -> None:
    """Chiamare `async_publish` direttamente (invece di passare da
    `async_refresh`) non avvia mai il reauth automatico: verificato che con
    la correzione lo fa, e che il servizio sollevi il proprio
    `HomeAssistantError`, non l'eccezione grezza dell'API."""
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup(hass, client_mock)
    freezer.tick(61)

    client_mock.release.side_effect = SwitchBotCanvasAuthError("token scaduto")

    with pytest.raises(HomeAssistantError) as errore:
        await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)
    await hass.async_block_till_done()

    assert not isinstance(errore.value, SwitchBotCanvasAuthError)

    flussi = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"].get("source") == "reauth" for f in flussi)


async def test_il_secondo_pannello_pubblica_anche_se_il_primo_fallisce(
    hass: HomeAssistant, client_mock, client_mock_2, freezer
) -> None:
    """Il primo pannello (DEV1) e' anche il primo che il servizio prova: senza
    azzerare i mock dopo il setup, `client_mock_2.release` risulterebbe
    "chiamato" per via della pubblicazione iniziale del setup, non per la
    chiamata al servizio — mascherando un fan-out che si fermasse al primo
    guasto (verificato: e' la stessa ragione per cui questo test non
    intercettava quella mutazione prima della correzione)."""
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup_two(hass, client_mock, client_mock_2)
    client_mock.release.reset_mock()
    client_mock_2.release.reset_mock()
    freezer.tick(61)

    client_mock.release.side_effect = SwitchBotCanvasAuthError("token scaduto")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)
    await hass.async_block_till_done()

    client_mock_2.release.assert_awaited()


async def test_refresh_aggiorna_tutti_i_pannelli_caricati(
    hass: HomeAssistant, client_mock, client_mock_2, freezer
) -> None:
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup_two(hass, client_mock, client_mock_2)
    client_mock.release.reset_mock()
    client_mock_2.release.reset_mock()

    freezer.tick(61)
    await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)
    await hass.async_block_till_done()

    client_mock.release.assert_awaited()
    client_mock_2.release.assert_awaited()


async def test_una_forzatura_non_si_propaga_ai_cicli_periodici_successivi(
    hass: HomeAssistant, client_mock, freezer
) -> None:
    """Il flag di forzatura vale per un solo giro: il ciclo periodico
    successivo, ad agenda invariata, deve tornare a saltare la pubblicazione
    come farebbe senza mai aver chiamato il servizio."""
    freezer.move_to("2026-08-23T12:00:00+00:00")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data=DATA,
        options={CONF_UPDATE_INTERVAL: 60},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_eink.SwitchBotCanvasClient", return_value=client_mock
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert client_mock.release.await_count == 1  # pubblicazione del setup

        freezer.tick(61)
        await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)
        await hass.async_block_till_done()
        assert client_mock.release.await_count == 2  # forzata dal servizio

        freezer.tick(61)
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

        # Ciclo periodico automatico, agenda invariata: se il flag di
        # forzatura non fosse stato consumato, ripubblicherebbe una terza
        # volta.
        assert client_mock.release.await_count == 2


# ---- entità diagnostiche -------------------------------------------------


async def test_il_sensore_di_ultima_pubblicazione_esiste(
    hass: HomeAssistant, client_mock
) -> None:
    await _setup(hass, client_mock)

    stato = hass.states.get(SENSOR_ID)
    assert stato is not None
    assert stato.state not in (None, "unknown", "unavailable")


async def test_il_sensore_si_aggiorna_dopo_il_refresh(
    hass: HomeAssistant, client_mock, freezer
) -> None:
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup(hass, client_mock)

    stato_prima = hass.states.get(SENSOR_ID)
    assert stato_prima is not None

    freezer.tick(61)
    await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)
    await hass.async_block_till_done()

    stato_dopo = hass.states.get(SENSOR_ID)
    assert dt_util.parse_datetime(stato_dopo.state) > dt_util.parse_datetime(
        stato_prima.state
    )


async def test_il_binary_sensor_di_autenticazione_e_a_posto(
    hass: HomeAssistant, client_mock
) -> None:
    await _setup(hass, client_mock)

    stato = hass.states.get(BINARY_SENSOR_ID)
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

    for entity_id in (SENSOR_ID, BINARY_SENSOR_ID):
        voce = entity_registry.async_get(entity_id)
        assert voce is not None
        assert voce.device_id == device.id


async def test_il_sensore_ha_la_device_class_timestamp(
    hass: HomeAssistant, client_mock
) -> None:
    await _setup(hass, client_mock)

    stato = hass.states.get(SENSOR_ID)
    assert stato.attributes.get("device_class") == "timestamp"


async def test_le_entita_diagnostiche_sono_diagnostiche(
    hass: HomeAssistant, client_mock
) -> None:
    await _setup(hass, client_mock)

    entity_registry = er.async_get(hass)
    for entity_id in (SENSOR_ID, BINARY_SENSOR_ID):
        voce = entity_registry.async_get(entity_id)
        assert voce is not None
        assert voce.entity_category is EntityCategory.DIAGNOSTIC


async def test_gli_unique_id_sono_quelli_attesi(
    hass: HomeAssistant, client_mock
) -> None:
    await _setup(hass, client_mock)

    entity_registry = er.async_get(hass)
    assert entity_registry.async_get(SENSOR_ID).unique_id == "DEV1_last_published"
    assert entity_registry.async_get(BINARY_SENSOR_ID).unique_id == "DEV1_auth"


async def test_ogni_pannello_ha_le_sue_entita_con_unique_id_distinti(
    hass: HomeAssistant, client_mock, client_mock_2
) -> None:
    await _setup_two(hass, client_mock, client_mock_2)

    entity_registry = er.async_get(hass)
    unique_ids = {
        entity_registry.async_get(entity_id).unique_id
        for entity_id in (SENSOR_ID, BINARY_SENSOR_ID, SENSOR_ID_2, BINARY_SENSOR_ID_2)
    }
    assert unique_ids == {
        "DEV1_last_published",
        "DEV1_auth",
        "DEV2_last_published",
        "DEV2_auth",
    }


async def test_available_resta_vero_anche_se_una_pubblicazione_fallisce(
    hass: HomeAssistant, client_mock, freezer
) -> None:
    """`CoordinatorEntity.available` seguirebbe `last_update_success`: le due
    entità diagnostiche devono restare disponibili anche quando il ciclo
    fallisce, perché è proprio in quel momento che servono."""
    freezer.move_to("2026-08-23T12:00:00+00:00")
    await _setup(hass, client_mock)
    freezer.tick(61)

    client_mock.release.side_effect = SwitchBotCanvasApiError(500, "boom")

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)
    await hass.async_block_till_done()

    for entity_id in (SENSOR_ID, BINARY_SENSOR_ID):
        stato = hass.states.get(entity_id)
        assert stato is not None
        assert stato.state != "unavailable"
