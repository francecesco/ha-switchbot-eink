"""Compilatore della dashboard: definizione dichiarativa → wire format."""
from __future__ import annotations

from .agenda import Event, build_agenda_page
from .compile import EntityValue, LayoutError, compile_page, components_hash
from .schema import CARD_TYPES, DEFAULT_PAGE_SLOT, PAGE_SLOTS, validate_page

__all__ = [
    "build_agenda_page",
    "CARD_TYPES",
    "compile_page",
    "components_hash",
    "DEFAULT_PAGE_SLOT",
    "EntityValue",
    "Event",
    "LayoutError",
    "PAGE_SLOTS",
    "validate_page",
]
