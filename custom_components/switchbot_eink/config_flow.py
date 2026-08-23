"""Config flow dell'integrazione."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.auth import CanvasAuth, Tokens
from .api.client import SwitchBotCanvasClient
from .api.const import REGIONS
from .api.errors import SwitchBotCanvasError
from .api.models import Device
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_TOKEN_TYPE,
    CONF_USER_ID,
    CONF_USERNAME,
    DOMAIN,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,
        vol.Required("region", default="eu"): vol.In(REGIONS),
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required("password"): str})


class SwitchBotEinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Login, scelta del pannello, e nessuna password su disco."""

    VERSION = 1

    def __init__(self) -> None:
        self._tokens: Tokens | None = None
        self._user_id: str | None = None
        self._region: str = "eu"
        self._username: str = ""
        self._devices: list[Device] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Chiede le credenziali e verifica che ci sia almeno un pannello."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

        session = async_get_clientsession(self.hass)
        self._region = user_input["region"]
        self._username = user_input["username"]
        auth = CanvasAuth(session, self._region)

        try:
            tokens = await auth.login(user_input["username"], user_input["password"])
            info = await auth.user_info(tokens.access_token, tokens.token_type)
            client = SwitchBotCanvasClient(session, self._region, tokens, info.user_id)
            devices = await client.list_eink_devices()
        except SwitchBotCanvasError:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_SCHEMA,
                errors={"base": "invalid_auth"},
            )

        if not devices:
            return self.async_abort(reason="no_devices_found")

        self._tokens = tokens
        self._user_id = info.user_id
        self._devices = devices

        return await self.async_step_device()

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fa scegliere quale pannello pilotare."""
        assert self._tokens is not None and self._user_id is not None

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

        region = entry.data[CONF_REGION]
        auth = CanvasAuth(async_get_clientsession(self.hass), region)

        try:
            tokens = await auth.login(
                entry.data[CONF_USERNAME], user_input["password"]
            )
            info = await auth.user_info(tokens.access_token, tokens.token_type)
        except SwitchBotCanvasError:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=STEP_REAUTH_SCHEMA,
                errors={"base": "invalid_auth"},
                description_placeholders={"username": entry.data.get(CONF_USERNAME, "")},
            )

        return self.async_update_reload_and_abort(
            entry,
            data_updates={
                CONF_ACCESS_TOKEN: tokens.access_token,
                CONF_REFRESH_TOKEN: tokens.refresh_token,
                CONF_TOKEN_TYPE: tokens.token_type,
                CONF_USER_ID: info.user_id,
            },
        )
