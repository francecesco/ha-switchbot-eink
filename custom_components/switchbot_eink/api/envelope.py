"""Funzioni pure di protocollo: header, URL, envelope delle risposte.

Nessuna I/O qui dentro, così restano banali da testare.
"""
from __future__ import annotations

import re
from typing import Any

from .const import BACKEND_BASE_TEMPLATE, DEFAULT_REGION, REGIONS, RESULT_OK
from .errors import SwitchBotCanvasApiError, SwitchBotCanvasAuthError

_BEARER_PREFIX = re.compile(r"^Bearer\s+", re.IGNORECASE)


def build_auth_header(access_token: str, token_type: str | None, region: str) -> str:
    """Costruisce il valore dell'header Authorization.

    Il client web usa "{token_type} {access_token}", ma sulla sola regione eu
    rimuove il prefisso Bearer e manda il token nudo. Ignorare questo dettaglio
    produce 401 senza spiegazione.
    """
    header = f"{token_type or 'Bearer'} {access_token}"
    if region.strip().lower() == "eu":
        header = _BEARER_PREFIX.sub("", header)
    return header


def normalize_region(value: str) -> str:
    """Normalizza il nome di una regione, rifiutando quelle sconosciute.

    `backend_base_url` ricade su `us` per qualunque valore non riconosciuto:
    è una rete di sicurezza ragionevole per il codice, ma pessima all'ingresso,
    dove un errore di battitura diventerebbe una richiesta al server sbagliato
    con l'header sbagliato, e un 401 che non spiega niente.
    """
    normalized = value.strip().lower()
    if normalized not in REGIONS:
        raise ValueError(f"regione {value!r} sconosciuta: usa una fra {', '.join(REGIONS)}")
    return normalized


def backend_base_url(region: str) -> str:
    """URL base del servizio productbiz per la regione data."""
    if region not in REGIONS:
        region = DEFAULT_REGION
    return BACKEND_BASE_TEMPLATE.format(region=region)


def unwrap_backend(payload: object) -> Any:
    """Estrae `data` da un envelope productbiz, sollevando sugli errori."""
    if not isinstance(payload, dict):
        raise SwitchBotCanvasApiError(-1, f"Risposta malformata: {payload!r}")
    code = payload.get("resultCode")
    if code != RESULT_OK:
        message = str(payload.get("message", ""))
        if code == 401:
            raise SwitchBotCanvasAuthError(f"[{code}] {message}")
        raise SwitchBotCanvasApiError(int(code) if code is not None else -1, message)
    return payload.get("data")


def unwrap_account(payload: object) -> Any:
    """Estrae `body` da un envelope dell'account service."""
    if not isinstance(payload, dict):
        raise SwitchBotCanvasAuthError(f"Risposta malformata: {payload!r}")
    code = payload.get("statusCode")
    if code != RESULT_OK:
        raise SwitchBotCanvasAuthError(f"[{code}] {payload.get('message', '')}")
    if "body" not in payload:
        raise SwitchBotCanvasAuthError("L'account service ha risposto senza body")
    return payload["body"]
