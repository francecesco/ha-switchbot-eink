"""Validazione della definizione dichiarativa della dashboard."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from .const import COLORS, DEFAULT_METRIC_TYPE, GRID_COLS, GRID_ROWS, METRIC_TYPES

CARD_TYPES: tuple[str, ...] = ("metric", "text", "divider", "frame", "image")
PAGE_SLOTS: tuple[str, ...] = ("custom1", "custom2", "custom3", "custom4")

DEFAULT_PAGE_NAME = "Home Assistant"


def _as_int(value: Any, what: str) -> int:
    """Accetta solo interi veri.

    `int(1.5)` darebbe 1 senza lamentarsi: in uno YAML scritto a mano un valore
    frazionario è un errore di battitura, non una richiesta di arrotondamento.
    I booleani in Python sono interi, quindi vanno esclusi a parte.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise vol.Invalid(f"{what} deve essere un intero, trovato {value!r}")
    return value


def _grid_tuple(value: Any) -> list[int]:
    """Valida [colonna, riga, larghezza, altezza] contro i limiti della griglia."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise vol.Invalid("grid deve essere [colonna, riga, larghezza, altezza]")
    col, row, span_w, span_h = (
        _as_int(item, nome)
        for item, nome in zip(value, ("colonna", "riga", "larghezza", "altezza"), strict=True)
    )
    if not 0 <= col < GRID_COLS:
        raise vol.Invalid(f"colonna {col} fuori dalle {GRID_COLS} colonne")
    if not 0 <= row < GRID_ROWS:
        raise vol.Invalid(f"riga {row} fuori dalle {GRID_ROWS} righe")
    if span_w < 1 or col + span_w > GRID_COLS:
        raise vol.Invalid(f"larghezza {span_w} da colonna {col} esce dalla griglia")
    if span_h < 1 or row + span_h > GRID_ROWS:
        raise vol.Invalid(f"altezza {span_h} da riga {row} esce dalla griglia")
    return [col, row, span_w, span_h]


def _position_tuple(value: Any) -> list[int]:
    """Valida [x, y, w, h] in pixel."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise vol.Invalid("position deve essere [x, y, larghezza, altezza] in pixel")
    return [
        _as_int(item, nome)
        for item, nome in zip(value, ("x", "y", "larghezza", "altezza"), strict=True)
    ]


STYLE_SCHEMA = vol.Schema(
    {
        vol.Optional("fontSize"): vol.All(int, vol.Range(min=8, max=200)),
        vol.Optional("fontWeight"): vol.All(int, vol.Range(min=100, max=900)),
        vol.Optional("align"): vol.In(("left", "center", "right")),
        vol.Optional("rotation"): vol.All(int, vol.Range(min=0, max=359)),
        vol.Optional("padding"): vol.All(int, vol.Range(min=0, max=64)),
        vol.Optional("radius"): vol.All(int, vol.Range(min=0, max=64)),
        vol.Optional("borderWidth"): vol.All(int, vol.Range(min=0, max=16)),
        vol.Optional("iconSize"): vol.In((16, 24, 32, 48, 64, 96)),
        vol.Optional("numberFontSize"): vol.All(int, vol.Range(min=8, max=200)),
        vol.Optional("labelFontSize"): vol.All(int, vol.Range(min=8, max=200)),
        vol.Optional("unitFontSize"): vol.All(int, vol.Range(min=8, max=200)),
        vol.Optional("textColor"): vol.In(COLORS),
        vol.Optional("backgroundColor"): vol.In(COLORS),
        vol.Optional("borderColor"): vol.In(COLORS),
        vol.Optional("fit"): vol.In(("contain", "cover")),
    }
)

CARD_SCHEMA = vol.Schema(
    {
        vol.Required("type"): vol.In(CARD_TYPES),
        vol.Optional("grid"): _grid_tuple,
        vol.Optional("position"): _position_tuple,
        vol.Optional("style", default=dict): STYLE_SCHEMA,
        vol.Optional("z", default=1): int,
        # metric
        vol.Optional("widget"): vol.In(METRIC_TYPES),
        vol.Optional("entity"): str,
        # Volutamente non validata contro KNOWN_ICONS: quella lista contiene solo
        # gli alias estratti dal renderer, il registro vero e' piu' ampio e non
        # enumerabile. Un nome sconosciuto ricade su un'icona di default.
        vol.Optional("icon"): str,
        vol.Optional("label"): str,
        vol.Optional("value"): str,
        vol.Optional("unit"): str,
        # text
        vol.Optional("text"): str,
        # image
        vol.Optional("src"): str,
        vol.Optional("alt"): str,
    }
)

PAGE_SCHEMA = vol.Schema(
    {
        vol.Required("page"): vol.In(PAGE_SLOTS),
        vol.Optional("name", default=DEFAULT_PAGE_NAME): str,
        vol.Required("cards"): [CARD_SCHEMA],
    }
)


def _check_card_invariants(card: dict[str, Any], index: int) -> None:
    has_grid = "grid" in card
    has_position = "position" in card

    if has_grid and has_position:
        raise vol.Invalid(f"card {index}: grid e position sono mutuamente esclusivi")
    if not has_grid and not has_position:
        raise vol.Invalid(f"card {index}: serve grid oppure position")

    if card["type"] == "metric" and "entity" not in card and "value" not in card:
        raise vol.Invalid(f"card {index}: una metric richiede entity oppure value")
    if card["type"] == "text" and "text" not in card:
        raise vol.Invalid(f"card {index}: una text richiede il campo text")
    if card["type"] == "image" and "src" not in card:
        raise vol.Invalid(f"card {index}: una image richiede il campo src")


def validate_page(raw: dict[str, Any]) -> dict[str, Any]:
    """Valida e normalizza la definizione di una pagina."""
    page: dict[str, Any] = PAGE_SCHEMA(raw)
    for index, card in enumerate(page["cards"]):
        _check_card_invariants(card, index)
        if card["type"] == "metric":
            card.setdefault("widget", DEFAULT_METRIC_TYPE)
    return page
