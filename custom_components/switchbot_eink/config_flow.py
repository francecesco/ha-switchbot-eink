"""Config flow dell'integrazione."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.auth import CanvasAuth, Tokens
from .api.client import SwitchBotCanvasClient
from .api.const import REGIONS
from .api.envelope import normalize_region
from .api.errors import SwitchBotCanvasAuthError, SwitchBotCanvasError
from .api.models import Device
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CALENDARS,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_TOKEN_TYPE,
    CONF_UPDATE_INTERVAL,
    CONF_USER_ID,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_PUBLISH_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_REGION, default="eu"): vol.In(REGIONS),
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


class SwitchBotEinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Login, scelta del pannello, e nessuna password su disco."""

    VERSION = 1

    def __init__(self) -> None:
        self._tokens: Tokens | None = None
        self._user_id: str | None = None
        self._region: str = "eu"
        self._username: str = ""
        self._devices: list[Device] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SwitchBotEinkOptionsFlow:
        return SwitchBotEinkOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Chiede le credenziali e verifica che ci sia almeno un pannello."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

        session = async_get_clientsession(self.hass)

        errore: str | None = None
        tokens: Tokens | None = None
        info = None
        devices: list[Device] = []
        try:
            region = normalize_region(user_input[CONF_REGION])
            auth = CanvasAuth(session, region)
            tokens = await auth.login(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            info = await auth.user_info(tokens.access_token, tokens.token_type)
            client = SwitchBotCanvasClient(session, region, tokens, info.user_id)
            devices = await client.list_eink_devices()
        except SwitchBotCanvasAuthError:
            errore = "invalid_auth"
        except SwitchBotCanvasError as err:
            _LOGGER.warning("Il backend SwitchBot non risponde come atteso: %s", err)
            errore = "cannot_connect"
        except Exception:  # noqa: BLE001
            # L'API e' privata e non documentata: una risposta di forma inattesa
            # arriva qui come KeyError o TypeError. Meglio un errore generico nel
            # form che un traceback dentro Home Assistant.
            _LOGGER.exception("Errore imprevisto durante il login a SwitchBot")
            errore = "unknown"

        if errore is not None:
            suggeriti = {k: v for k, v in user_input.items() if k != CONF_PASSWORD}
            return self.async_show_form(
                step_id="user",
                data_schema=self.add_suggested_values_to_schema(
                    STEP_USER_SCHEMA, suggeriti
                ),
                errors={"base": errore},
            )

        if not devices:
            return self.async_abort(reason="no_devices_found")

        self._region = region
        self._username = user_input[CONF_USERNAME]
        self._tokens = tokens
        self._user_id = info.user_id
        self._devices = devices

        return await self.async_step_device()

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fa scegliere quale pannello pilotare."""
        if self._tokens is None or self._user_id is None:
            # Stato interno mancante: un flusso ripreso male, non un caso da
            # far esplodere. Si riparte dal login.
            return await self.async_step_user()

        if user_input is None:
            return self.async_show_form(
                step_id="device",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_DEVICE_ID): vol.In(
                            {d.device_id: d.device_name for d in self._devices}
                        )
                    }
                ),
            )

        device_id = user_input[CONF_DEVICE_ID]
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured()

        device = next(d for d in self._devices if d.device_id == device_id)

        return self.async_create_entry(
            title=device.device_name or "SwitchBot E-Ink",
            data={
                CONF_REGION: self._region,
                CONF_USERNAME: self._username,
                CONF_ACCESS_TOKEN: self._tokens.access_token,
                CONF_REFRESH_TOKEN: self._tokens.refresh_token,
                CONF_TOKEN_TYPE: self._tokens.token_type,
                CONF_USER_ID: self._user_id,
                CONF_DEVICE_ID: device.device_id,
                CONF_DEVICE_NAME: device.device_name,
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Il refresh token non è più valido: serve di nuovo la password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Rifà il login e riscrive i soli token, senza toccare il resto."""
        entry = self._get_reauth_entry()

        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=STEP_REAUTH_SCHEMA,
                description_placeholders={"username": entry.data.get(CONF_USERNAME, "")},
            )

        session = async_get_clientsession(self.hass)

        errore: str | None = None
        tokens: Tokens | None = None
        info = None
        devices: list[Device] = []
        try:
            region = normalize_region(entry.data[CONF_REGION])
            auth = CanvasAuth(session, region)
            tokens = await auth.login(
                entry.data[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            info = await auth.user_info(tokens.access_token, tokens.token_type)
            client = SwitchBotCanvasClient(session, region, tokens, info.user_id)
            devices = await client.list_eink_devices()
        except SwitchBotCanvasAuthError:
            errore = "invalid_auth"
        except SwitchBotCanvasError as err:
            _LOGGER.warning("Il backend SwitchBot non risponde come atteso: %s", err)
            errore = "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Errore imprevisto durante il login a SwitchBot")
            errore = "unknown"

        if errore is not None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=STEP_REAUTH_SCHEMA,
                errors={"base": errore},
                description_placeholders={"username": entry.data.get(CONF_USERNAME, "")},
            )

        if all(d.device_id != entry.data[CONF_DEVICE_ID] for d in devices):
            return self.async_abort(reason="account_mismatch")

        return self.async_update_reload_and_abort(
            entry,
            data_updates={
                CONF_ACCESS_TOKEN: tokens.access_token,
                CONF_REFRESH_TOKEN: tokens.refresh_token,
                CONF_TOKEN_TYPE: tokens.token_type,
                CONF_USER_ID: info.user_id,
            },
        )


class SwitchBotEinkOptionsFlow(OptionsFlow):
    """Un solo campo: ogni quanto ripubblicare."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        attuale = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UPDATE_INTERVAL, default=attuale): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_PUBLISH_INTERVAL)
                    ),
                    vol.Optional(
                        CONF_CALENDARS,
                        default=self.config_entry.options.get(CONF_CALENDARS, []),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="calendar", multiple=True)
                    ),
                }
            ),
        )
