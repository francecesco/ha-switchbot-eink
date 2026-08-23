"""Compila una definizione di pagina in componenti wire format.

Funzione pura: il rendering dei template e la lettura degli stati arrivano da
due callback, così questo modulo non dipende da Home Assistant e si testa senza.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .const import USABLE_HEIGHT, USABLE_WIDTH
from .grid import Rect, grid_to_rect, rect_fits, rects_overlap, to_canvas
from .widgets import to_wire

VALORE_ASSENTE = "—"

# Mappa dai tipi di card astratti ai tipi di widget del renderer.
_WIDGET_BY_CARD_TYPE: dict[str, str] = {
    "text": "text",
    "divider": "divider",
    "frame": "decorFrame",
    "image": "image",
}


class LayoutError(Exception):
    """La definizione è sintatticamente valida ma non produce un canvas sensato."""


@dataclass(frozen=True, slots=True)
class EntityValue:
    """Stato di un'entità, già in forma di stringa."""

    state: str
    unit: str | None


Renderer = Callable[[str], str]
EntityResolver = Callable[[str], EntityValue | None]


def _rect_for(card: dict[str, Any]) -> Rect:
    if "grid" in card:
        col, row, span_w, span_h = card["grid"]
        return grid_to_rect(col, row, span_w, span_h)
    x, y, w, h = card["position"]
    return Rect(x, y, w, h)


def _content_for(
    card: dict[str, Any], render: Renderer, resolve: EntityResolver
) -> dict[str, Any]:
    card_type = card["type"]

    # Una card con `template: false` porta contenuti che non sono scritti
    # dall'utente — i titoli degli eventi di calendario, per esempio — e che
    # eseguire come Jinja sarebbe un'iniezione.
    rendi = render if card.get("template", True) else (lambda testo: testo)

    if card_type in ("divider", "frame"):
        return {}

    if card_type == "image":
        content = {"src": rendi(card["src"])}
        if "alt" in card:
            content["alt"] = rendi(card["alt"])
        return content

    if card_type == "text":
        return {"text": rendi(card["text"])}

    # metric
    entity_value = resolve(card["entity"]) if "entity" in card else None

    if "value" in card:
        value = rendi(card["value"])
    elif entity_value is not None:
        value = entity_value.state
    else:
        value = VALORE_ASSENTE

    content: dict[str, Any] = {"value": value}

    if "label" in card:
        content["label"] = rendi(card["label"])
    if "icon" in card:
        content["icon"] = card["icon"]

    if "unit" in card:
        content["unit"] = rendi(card["unit"])
    elif entity_value is not None and entity_value.unit:
        content["unit"] = entity_value.unit

    return content


def _widget_type_for(card: dict[str, Any]) -> str:
    if card["type"] == "metric":
        return card["widget"]
    return _WIDGET_BY_CARD_TYPE[card["type"]]


def compile_page(
    page: dict[str, Any], render: Renderer, resolve: EntityResolver
) -> list[dict[str, str]]:
    """Trasforma una pagina validata nella lista di componenti da inviare."""
    componenti: list[dict[str, str]] = []
    rettangoli: list[tuple[int, Rect]] = []

    for index, card in enumerate(page["cards"]):
        try:
            rect = _rect_for(card)
        except ValueError as err:
            raise LayoutError(f"card {index}: {err}") from err

        if not rect_fits(rect):
            raise LayoutError(
                f"card {index}: il rettangolo {rect} esce dall'area utile "
                f"{USABLE_WIDTH}x{USABLE_HEIGHT}"
            )

        for altro_index, altro_rect in rettangoli:
            if rects_overlap(rect, altro_rect):
                raise LayoutError(
                    f"le card {altro_index} e {index} si sovrappongono"
                )

        rettangoli.append((index, rect))

        widget_type = _widget_type_for(card)
        componenti.append(
            to_wire(
                component_id=str(index + 1),
                widget_type=widget_type,
                name=f"{page['name']} #{index + 1}",
                rect=to_canvas(rect),
                content=_content_for(card, render, resolve),
                style=card.get("style", {}),
                z=card.get("z", 1),
            )
        )

    return componenti


def components_hash(components: list[dict[str, str]]) -> str:
    """Impronta stabile della lista, per non ripubblicare un canvas identico."""
    canonical = json.dumps(components, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
