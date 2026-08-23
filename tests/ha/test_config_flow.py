"""Test del config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.switchbot_eink.api.auth import Tokens, UserInfo
from custom_components.switchbot_eink.api.errors import (
    SwitchBotCanvasApiError,
    SwitchBotCanvasAuthError,
)
from custom_components.switchbot_eink.api.models import Device
from custom_components.switchbot_eink.const import (
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_UPDATE_INTERVAL,
    CONF_USER_ID,
    DOMAIN,
)

TOKENS = Tokens(access_token="AT", refresh_token="RT", token_type="Bearer")
UTENTE = UserInfo(user_id="user-1", email="mario@example.test")
PANNELLO = Device(
    device_id="DEV1", device_name="Cucina", device_type="W1070000", is_share=False
)
ALTRO_PANNELLO = Device(
    device_id="DEV2", device_name="Salotto", device_type="W1070000", is_share=False
)

CREDENZIALI = {
    "username": "mario@example.test",
    "password": "segreta",
    "region": "eu",
}

PERCORSO_AUTH = "custom_components.switchbot_eink.config_flow.CanvasAuth"
PERCORSO_CLIENT = "custom_components.switchbot_eink.config_flow.SwitchBotCanvasClient"


def _mock_auth(mock_cls) -> None:
    istanza = mock_cls.return_value
    istanza.login = AsyncMock(return_value=TOKENS)
    istanza.user_info = AsyncMock(return_value=UTENTE)


def _mock_client(mock_cls, devices=None) -> None:
    istanza = mock_cls.return_value
    istanza.list_eink_devices = AsyncMock(
        return_value=[PANNELLO] if devices is None else devices
    )


async def test_flusso_completo_crea_la_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"

    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_ID: "DEV1"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Cucina"
    assert result["data"][CONF_REFRESH_TOKEN] == "RT"
    assert result["data"][CONF_USER_ID] == "user-1"
    assert result["data"][CONF_DEVICE_ID] == "DEV1"
    assert result["data"][CONF_REGION] == "eu"


async def test_la_password_non_viene_persistita(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_ID: "DEV1"}
        )
        await hass.async_block_till_done()

    assert "password" not in result["data"]


async def test_credenziali_errate_mostrano_l_errore(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PERCORSO_AUTH) as auth:
        auth.return_value.login = AsyncMock(side_effect=SwitchBotCanvasAuthError("no"))
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_errore_di_rete_in_login_mostra_cannot_connect(
    hass: HomeAssistant,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PERCORSO_AUTH) as auth:
        auth.return_value.login = AsyncMock(
            side_effect=SwitchBotCanvasApiError(500, "boom")
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_risposta_inattesa_in_login_mostra_errore_sconosciuto(
    hass: HomeAssistant,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PERCORSO_AUTH) as auth:
        auth.return_value.login = AsyncMock(side_effect=KeyError("access_token"))
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_nessun_pannello_interrompe_il_flusso(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client, devices=[])
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_lo_stesso_dispositivo_non_si_configura_due_volte(
    hass: HomeAssistant,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data={}).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_ID: "DEV1"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_il_form_device_offre_tutti_i_pannelli(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client, devices=[PANNELLO, ALTRO_PANNELLO])
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"
    offerte = result["data_schema"].schema[CONF_DEVICE_ID].container
    assert set(offerte) == {"DEV1", "DEV2"}

    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client, devices=[PANNELLO, ALTRO_PANNELLO])
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_ID: "DEV2"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Salotto"
    assert result["data"][CONF_DEVICE_ID] == "DEV2"


async def test_reauth_riscrive_i_token_senza_creare_una_entry(
    hass: HomeAssistant,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.switchbot_eink.const import (
        CONF_ACCESS_TOKEN,
        CONF_DEVICE_NAME,
        CONF_REGION,
        CONF_TOKEN_TYPE,
        CONF_USERNAME,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={
            CONF_REGION: "eu",
            CONF_USERNAME: "mario@example.test",
            CONF_ACCESS_TOKEN: "vecchio",
            CONF_REFRESH_TOKEN: "vecchio-rt",
            CONF_TOKEN_TYPE: "Bearer",
            CONF_USER_ID: "user-1",
            CONF_DEVICE_ID: "DEV1",
            CONF_DEVICE_NAME: "Cucina",
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "nuova"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == "AT"
    assert entry.data[CONF_REFRESH_TOKEN] == "RT"


async def test_reauth_con_password_errata_mostra_l_errore(hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.switchbot_eink.const import CONF_REGION

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={
            CONF_REGION: "eu",
            "access_token": "vecchio",
            CONF_REFRESH_TOKEN: "vecchio-rt",
            "token_type": "Bearer",
            CONF_USER_ID: "user-1",
            CONF_DEVICE_ID: "DEV1",
            "username": "mario@example.test",
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with patch(PERCORSO_AUTH) as auth:
        auth.return_value.login = AsyncMock(side_effect=SwitchBotCanvasAuthError("no"))
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "sbagliata"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_con_errore_di_rete_mostra_cannot_connect(
    hass: HomeAssistant,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.switchbot_eink.const import CONF_REGION

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={
            CONF_REGION: "eu",
            "access_token": "vecchio",
            CONF_REFRESH_TOKEN: "vecchio-rt",
            "token_type": "Bearer",
            CONF_USER_ID: "user-1",
            CONF_DEVICE_ID: "DEV1",
            "username": "mario@example.test",
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with patch(PERCORSO_AUTH) as auth:
        auth.return_value.login = AsyncMock(
            side_effect=SwitchBotCanvasApiError(500, "boom")
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "nuova"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_con_risposta_inattesa_mostra_errore_sconosciuto(
    hass: HomeAssistant,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.switchbot_eink.const import CONF_REGION

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={
            CONF_REGION: "eu",
            "access_token": "vecchio",
            CONF_REFRESH_TOKEN: "vecchio-rt",
            "token_type": "Bearer",
            CONF_USER_ID: "user-1",
            CONF_DEVICE_ID: "DEV1",
            "username": "mario@example.test",
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with patch(PERCORSO_AUTH) as auth:
        auth.return_value.login = AsyncMock(side_effect=KeyError("access_token"))
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "nuova"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_reauth_con_regione_in_maiuscolo_viene_normalizzata(
    hass: HomeAssistant,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.switchbot_eink.const import (
        CONF_ACCESS_TOKEN,
        CONF_REGION,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={
            CONF_REGION: "EU",
            "access_token": "vecchio",
            CONF_REFRESH_TOKEN: "vecchio-rt",
            "token_type": "Bearer",
            CONF_USER_ID: "user-1",
            CONF_DEVICE_ID: "DEV1",
            "username": "mario@example.test",
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "nuova"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == "AT"
    # La regione passata a CanvasAuth deve essere normalizzata ("eu"), non il
    # valore grezzo salvato nella entry ("EU"): altrimenti build_auth_header
    # e device_base_url la trattano in modo diverso e il 401 non spiega niente.
    assert auth.call_args.args[1] == "eu"


async def test_reauth_con_account_diverso_interrompe_il_flusso(
    hass: HomeAssistant,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.switchbot_eink.const import CONF_REGION

    dati_originali = {
        CONF_REGION: "eu",
        "access_token": "vecchio",
        CONF_REFRESH_TOKEN: "vecchio-rt",
        "token_type": "Bearer",
        CONF_USER_ID: "user-1",
        CONF_DEVICE_ID: "DEV1",
        "username": "mario@example.test",
    }
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="DEV1", data=dict(dati_originali)
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        # L'account con cui si rifà il login non possiede più "DEV1", solo
        # un pannello diverso: e' un altro account SwitchBot.
        _mock_client(client, devices=[ALTRO_PANNELLO])
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "nuova"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "account_mismatch"
    assert dict(entry.data) == dati_originali


async def test_reauth_su_una_entry_reale_creata_dal_flusso_utente(
    hass: HomeAssistant,
) -> None:
    """L'unico test di reauth che non costruisce la entry a mano.

    Se `async_step_device` smettesse di salvare `CONF_USERNAME`, il reauth
    reale si romperebbe: nessuno degli altri test se ne accorgerebbe, perché
    tutti si costruiscono la entry manualmente con `CONF_USERNAME` già dentro.
    """
    from pytest_homeassistant_custom_component.common import start_reauth_flow

    from custom_components.switchbot_eink.const import CONF_ACCESS_TOKEN

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_ID: "DEV1"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await start_reauth_flow(hass, entry)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "nuova"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == "AT"


async def test_le_opzioni_impongono_l_intervallo_minimo(hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_UPDATE_INTERVAL: 10}
        )


async def test_le_opzioni_valide_finiscono_nella_entry(hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UPDATE_INTERVAL: 300}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UPDATE_INTERVAL] == 300
