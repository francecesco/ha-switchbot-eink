"""Modelli di dominio dell'API canvas."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_CUSTOM_SLOT = re.compile(r"^custom([1-4])$")


def page_slot_to_template_type(page_slot: str) -> int:
    """1 per la home, 0 per le pagine custom."""
    return 1 if page_slot == "home" else 0


def page_slot_to_sort_order(page_slot: str) -> int:
    """home → 1, custom1..custom4 → 1..4, tutto il resto → 0."""
    if page_slot == "home":
        return 1
    match = _CUSTOM_SLOT.match(page_slot)
    return int(match.group(1)) if match else 0


def sort_order_to_page_slot(sort_order: int, template_type: int) -> str:
    """Ricava lo slot da `sortOrder` e `templateType`.

    La risposta del backend non contiene lo slot: va dedotto. Servono entrambi i
    campi, perche' la home e `custom1` hanno tutti e due `sortOrder` 1 e si
    distinguono solo per `templateType`.
    """
    if template_type == 1:
        return "home"
    if 1 <= sort_order <= 4:
        return f"custom{sort_order}"
    return "unassigned"


@dataclass(frozen=True, slots=True)
class Device:
    """Un dispositivo dell'account."""

    device_id: str
    device_name: str
    device_type: str
    is_share: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Device:
        return cls(
            device_id=str(payload["deviceID"]),
            device_name=str(payload.get("deviceName", "")),
            device_type=str(payload.get("deviceType", "")),
            is_share=bool(payload.get("isShare", False)),
        )


@dataclass(frozen=True, slots=True)
class TemplateSummary:
    """Voce della lista dei template."""

    template_id: int
    name: str
    page_slot: str
    template_type: int = 0


@dataclass(slots=True)
class Template:
    """Un template pronto per essere inviato.

    `components` contiene già i componenti nel wire format, con `css` ed `extra`
    serializzati come stringhe JSON.
    """

    template_id: int | None
    name: str
    page_slot: str
    device_id: str
    components: list[dict[str, Any]] = field(default_factory=list)

    @property
    def template_type(self) -> int:
        return page_slot_to_template_type(self.page_slot)

    @property
    def sort_order(self) -> int:
        return page_slot_to_sort_order(self.page_slot)
