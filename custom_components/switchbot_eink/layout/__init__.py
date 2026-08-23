"""Compilatore della dashboard: definizione dichiarativa → wire format."""
from __future__ import annotations

from .compile import EntityValue, LayoutError, compile_page, components_hash
from .schema import CARD_TYPES, DEFAULT_PAGE_SLOT, PAGE_SLOTS, validate_page

__all__ = [
    "CARD_TYPES",
    "DEFAULT_PAGE_SLOT",
    "PAGE_SLOTS",
    "EntityValue",
    "LayoutError",
    "compile_page",
    "components_hash",
    "validate_page",
]
