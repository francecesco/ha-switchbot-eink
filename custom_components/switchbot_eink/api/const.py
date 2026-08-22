"""Costanti dell'API privata del canvas editor SwitchBot.

Ricavate per reverse engineering dai bundle JavaScript pubblici di
https://e-ink-home-dashboard.switch-bot.com. Non sono documentazione ufficiale.
"""
from __future__ import annotations

from typing import Final

ACCOUNT_BASE_URL: Final = "https://account.api.switchbot.net"
BACKEND_BASE_TEMPLATE: Final = "https://wonderlabs.{region}.api.switchbot.net/productbiz"

CLIENT_ID: Final = "pg6fbtxbi7q3o2n4zba852d5lh"
SERVICE_ID: Final = "weather_station"

REGIONS: Final[tuple[str, ...]] = ("us", "ap", "eu")
DEFAULT_REGION: Final = "us"

DEVICE_TYPE_EINK: Final = "W1070000"
PANEL_ID: Final = "eink-7in3"

DEVICE_INFO: Final[dict[str, str]] = {
    "deviceName": "Web",
    "deviceId": "hub-web",
    "appVersion": "0.0.0",
    "model": "Web",
}

RESULT_OK: Final = 100

PATH_LOGIN: Final = "/account/api/v1/user/login"
PATH_REFRESH: Final = "/account/api/v1/user/token/refresh"
PATH_USERINFO: Final = "/account/api/v1/user/userinfo"

PATH_DEVICE_LIST: Final = "/device/v1/manage/getDeviceList"

PATH_TPL_LIST: Final = "/web/v1/user/templates/list"
PATH_TPL_INFO: Final = "/web/v1/user/templates/info"
PATH_TPL_CREATE: Final = "/web/v1/user/templates/create"
PATH_TPL_UPDATE: Final = "/web/v1/user/templates/update"
PATH_TPL_DEL: Final = "/web/v1/user/templates/del"
PATH_TPL_RELEASE: Final = "/web/v1/user/templates/release"
PATH_TPL_PREVIEW: Final = "/web/v1/user/templates/preview"
