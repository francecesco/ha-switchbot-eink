"""Serializzazione di un componente nel wire format del backend.

Due dettagli che è facile sbagliare e che il backend non perdona:
`css` ed `extra` viaggiano come stringhe JSON, e l'`id` deve essere una stringa
che rappresenta un intero positivo, altrimenti collassa a "0" e tutti i
componenti si sovrascrivono a vicenda.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .const import (
    CONTENT_WHITELIST,
    MAX_COMPONENT_ID,
    STYLE_DEFAULTS,
    STYLE_WHITELIST,
)
from .grid import Rect

_NUMERIC_ID = re.compile(r"^[1-9]\d*$")


def validate_component_id(component_id: str) -> str:
    """Verifica che l'id sia accettabile per il backend."""
    if not _NUMERIC_ID.match(component_id):
        raise ValueError(
            f"id componente {component_id!r}: serve un intero positivo come stringa"
        )
    if int(component_id) > MAX_COMPONENT_ID:
        raise ValueError(f"id componente {component_id!r}: supera {MAX_COMPONENT_ID}")
    return component_id


def _filter_style(widget_type: str, style: dict[str, Any]) -> dict[str, Any]:
    merged = {**STYLE_DEFAULTS.get(widget_type, {}), **style}
    allowed = STYLE_WHITELIST.get(widget_type)
    if allowed is None:
        return merged
    return {key: merged[key] for key in allowed if key in merged}


def _filter_content(widget_type: str, content: dict[str, Any]) -> dict[str, Any]:
    allowed = CONTENT_WHITELIST.get(widget_type)
    if allowed is None:
        return dict(content)
    return {key: content[key] for key in allowed if key in content}


def to_wire(
    component_id: str,
    widget_type: str,
    name: str,
    rect: Rect,
    content: dict[str, Any],
    style: dict[str, Any] | None = None,
    data_mode: str = "text",
    z: int = 1,
) -> dict[str, str]:
    """Produce il componente pronto da inserire in `Template.components`."""
    validate_component_id(component_id)

    css: dict[str, Any] = {
        "x": rect.x,
        "y": rect.y,
        "w": rect.w,
        "h": rect.h,
        "z": z,
        **_filter_style(widget_type, style or {}),
    }

    extra: dict[str, Any] = {
        "dataMode": data_mode,
        "source": "custom",
        "refresh": "1h",
        "content": _filter_content(widget_type, content),
        "locked": False,
        "visible": True,
    }

    return {
        "id": component_id,
        "type": widget_type,
        "name": name,
        "css": json.dumps(css, separators=(",", ":"), ensure_ascii=False),
        "extra": json.dumps(extra, separators=(",", ":"), ensure_ascii=False),
    }
