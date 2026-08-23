"""Costanti dell'integrazione."""
from __future__ import annotations

from typing import Final

from homeassistant.const import CONF_USERNAME as CONF_USERNAME  # noqa: F401 — re-export

DOMAIN: Final = "switchbot_eink"

CONF_REGION: Final = "region"
CONF_ACCESS_TOKEN: Final = "access_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_TOKEN_TYPE: Final = "token_type"
CONF_USER_ID: Final = "user_id"
CONF_DEVICE_ID: Final = "device_id"
CONF_DEVICE_NAME: Final = "device_name"
CONF_TEMPLATE_ID: Final = "template_id"
CONF_PAGE_SLOT: Final = "page_slot"
CONF_UPDATE_INTERVAL: Final = "update_interval"

# Da allineare alla cadenza misurata sul dispositivo (Task 5).
DEFAULT_UPDATE_INTERVAL: Final = 900  # secondi
MIN_PUBLISH_INTERVAL: Final = 60  # secondi, vincolo di spec

DEFAULT_PAGE_SLOT: Final = "custom1"

SERVICE_REFRESH: Final = "refresh"
SERVICE_PUSH_TEXT: Final = "push_text"
