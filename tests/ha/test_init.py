"""Test di async_setup_entry: costruzione del client, coordinator, ciclo di vita."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.switchbot_eink.api.auth import Tokens
from custom_components.switchbot_eink.const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_TOKEN_TYPE,
    CONF_UPDATE_INTERVAL,
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


async def test_lagenda_viene_ripubblicata_a_ogni_intervallo(
    hass: HomeAssistant, freezer
) -> None:
    """Regressione (C1): `DataUpdateCoordinator` arma il timer periodico solo
    se ha almeno un ascoltatore. Senza l'ascoltatore finto aggiunto in
    `async_setup_entry`, `publish` verrebbe chiamato una volta al setup e mai
    piu', ed e' esattamente cio' che questo test avrebbe dovuto intercettare
    prima della review."""
    freezer.move_to("2026-08-23T12:00:00+00:00")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data=dict(DATI),
        options={CONF_UPDATE_INTERVAL: 60},
    )
    entry.add_to_hass(hass)

    publish_mock = AsyncMock(return_value=True)
    with patch(PERCORSO_CLIENT) as client_cls:
        _mock_client(client_cls)
        with patch(PERCORSO_PUBLISH, publish_mock):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            assert publish_mock.await_count == 1

            for _ in range(3):
                freezer.tick(timedelta(seconds=60))
                async_fire_time_changed(hass, dt_util.utcnow())
                await hass.async_block_till_done()

    assert publish_mock.await_count >= 3


async def test_le_opzioni_cambiate_ricaricano_la_entry_con_il_nuovo_intervallo(
    hass: HomeAssistant, entry
) -> None:
    entry.add_to_hass(hass)

    with patch(PERCORSO_CLIENT) as client_cls:
        _mock_client(client_cls)
        with patch(PERCORSO_PUBLISH, AsyncMock(return_value=True)):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

            hass.config_entries.async_update_entry(
                entry, options={CONF_UPDATE_INTERVAL: 300}
            )
            await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.update_interval == timedelta(seconds=300)


async def test_un_rinnovo_del_token_non_ricarica_la_entry(
    hass: HomeAssistant, entry
) -> None:
    """`_persist_tokens` chiama `async_update_entry` su `entry.data`: non deve
    far scattare lo stesso listener di ricarica delle opzioni, altrimenti un
    rinnovo del token ricarica la entry e la ricarica rinnova/ripersiste di
    nuovo, all'infinito."""
    entry.add_to_hass(hass)

    with patch(PERCORSO_CLIENT) as client_cls:
        _mock_client(client_cls)
        with patch(PERCORSO_PUBLISH, AsyncMock(return_value=True)):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            coordinatore_prima = entry.runtime_data

            with patch.object(
                hass.config_entries, "async_reload", AsyncMock()
            ) as reload_mock:
                hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_ACCESS_TOKEN: "NUOVO"}
                )
                await hass.async_block_till_done()

    reload_mock.assert_not_awaited()
    assert entry.runtime_data is coordinatore_prima


async def test_unload_scarica_la_entry(hass: HomeAssistant, entry) -> None:
    entry.add_to_hass(hass)

    with patch(PERCORSO_CLIENT) as client_cls:
        _mock_client(client_cls)
        with patch(PERCORSO_PUBLISH, AsyncMock(return_value=True)):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_unload_invoca_async_unload_platforms(hass: HomeAssistant, entry) -> None:
    """Con `PLATFORMS = []` un `async_unload_entry` che si limitasse a
    `return True` produrrebbe comunque `entry.state == NOT_LOADED`, perche'
    con zero piattaforme la pulizia che conta avviene nei callback che il
    nucleo di Home Assistant registra ed esegue a prescindere dal corpo di
    questa funzione. L'unico modo per osservare che rilascia davvero le
    risorse (oggi un no-op, domani no) e' verificare che la chiamata avvenga.
    """
    entry.add_to_hass(hass)

    with patch(PERCORSO_CLIENT) as client_cls:
        _mock_client(client_cls)
        with patch(PERCORSO_PUBLISH, AsyncMock(return_value=True)):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

            with patch.object(
                hass.config_entries,
                "async_unload_platforms",
                wraps=hass.config_entries.async_unload_platforms,
            ) as unload_platforms_spia:
                assert await hass.config_entries.async_unload(entry.entry_id)
                await hass.async_block_till_done()

    unload_platforms_spia.assert_awaited_once()


async def test_il_token_type_non_ignorato_nella_costruzione_del_client(
    hass: HomeAssistant,
) -> None:
    """Un `token_type` diverso da 'Bearer' deve arrivare al client cosi' com'e'."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={**DATI, CONF_TOKEN_TYPE: "Custom"},
    )
    entry.add_to_hass(hass)

    with patch(PERCORSO_CLIENT) as client_cls:
        _mock_client(client_cls)
        with patch(PERCORSO_PUBLISH, AsyncMock(return_value=True)):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

    tokens_usati = client_cls.call_args.args[2]
    assert tokens_usati.token_type == "Custom"
