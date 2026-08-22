"""Client dell'API privata del canvas SwitchBot E-Ink Home Dashboard."""
from __future__ import annotations

from .auth import CanvasAuth, Tokens, UserInfo
from .client import SwitchBotCanvasClient
from .errors import (
    SwitchBotCanvasApiError,
    SwitchBotCanvasAuthError,
    SwitchBotCanvasError,
)
from .models import Device, Template, TemplateSummary

__all__ = [
    "CanvasAuth",
    "Device",
    "SwitchBotCanvasApiError",
    "SwitchBotCanvasAuthError",
    "SwitchBotCanvasClient",
    "SwitchBotCanvasError",
    "Template",
    "TemplateSummary",
    "Tokens",
    "UserInfo",
]
