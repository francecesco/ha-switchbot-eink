"""Eccezioni dello strato API."""
from __future__ import annotations


class SwitchBotCanvasError(Exception):
    """Errore generico nel dialogo con il backend SwitchBot."""


class SwitchBotCanvasAuthError(SwitchBotCanvasError):
    """Credenziali o token non validi: serve un nuovo login."""


class SwitchBotCanvasApiError(SwitchBotCanvasError):
    """Il backend ha risposto con un codice di errore applicativo."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
