"""Griglia 12×6 sull'area utile del pannello."""
from __future__ import annotations

from dataclasses import dataclass

from .const import (
    DEFAULT_GUTTER,
    GRID_COLS,
    GRID_ROWS,
    USABLE_HEIGHT,
    USABLE_LEFT,
    USABLE_TOP,
    USABLE_WIDTH,
)


@dataclass(frozen=True, slots=True)
class Rect:
    """Un rettangolo in pixel sull'area utile."""

    x: int
    y: int
    w: int
    h: int


def _track_edges(total: int, count: int, gutter: int) -> tuple[list[int], list[int]]:
    """Bordi di inizio e fine di ogni traccia, già arrotondati.

    Arrotondare i bordi una volta sola, invece di arrotondare posizione e
    dimensione separatamente, evita che i due errori si sommino: è ciò che
    garantisce che il distacco fra due celle adiacenti sia sempre esattamente
    la gutter, e non la gutter più o meno un pixel.
    """
    cell = (total - gutter * (count - 1)) / count
    pitch = cell + gutter
    starts = [round(index * pitch) for index in range(count)]
    ends = [round(index * pitch + cell) for index in range(count)]
    return starts, ends


def grid_to_rect(
    col: int, row: int, span_w: int, span_h: int, gutter: int = DEFAULT_GUTTER
) -> Rect:
    """Converte una posizione di griglia in pixel.

    Le celle hanno dimensione frazionaria. Arrotondiamo i bordi delle tracce
    una volta sola e ricaviamo la larghezza come differenza fra bordi già
    arrotondati, così il distacco fra celle adiacenti è sempre esattamente la
    gutter e uno span pieno copre esattamente l'area utile.
    """
    if span_w < 1 or span_h < 1:
        raise ValueError("span_w e span_h devono valere almeno 1")
    if not 0 <= col < GRID_COLS:
        raise ValueError(f"colonna {col} fuori dalla griglia a {GRID_COLS} colonne")
    if not 0 <= row < GRID_ROWS:
        raise ValueError(f"riga {row} fuori dalla griglia a {GRID_ROWS} righe")
    if col + span_w > GRID_COLS:
        raise ValueError(f"larghezza {span_w} da colonna {col} esce dalla griglia")
    if row + span_h > GRID_ROWS:
        raise ValueError(f"altezza {span_h} da riga {row} esce dalla griglia")

    col_starts, col_ends = _track_edges(USABLE_WIDTH, GRID_COLS, gutter)
    row_starts, row_ends = _track_edges(USABLE_HEIGHT, GRID_ROWS, gutter)

    x = col_starts[col]
    y = row_starts[row]

    return Rect(
        x=x,
        y=y,
        w=col_ends[col + span_w - 1] - x,
        h=row_ends[row + span_h - 1] - y,
    )


def rect_fits(rect: Rect) -> bool:
    """Vero se il rettangolo sta interamente dentro l'area utile."""
    return (
        rect.x >= 0
        and rect.y >= 0
        and rect.w > 0
        and rect.h > 0
        and rect.x + rect.w <= USABLE_WIDTH
        and rect.y + rect.h <= USABLE_HEIGHT
    )


def rects_overlap(a: Rect, b: Rect) -> bool:
    """Vero se i due rettangoli si intersecano. Il contatto sul bordo non conta."""
    return not (
        a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y
    )


def to_canvas(rect: Rect) -> Rect:
    """Traduce un rettangolo dall'area utile alle coordinate fisiche del pannello.

    E' l'unico punto del progetto che sa dove l'area utile comincia. Tutto il
    resto dello strato `layout` ragiona con origine in (0, 0), cosi' chi scrive
    una pagina non deve sapere che esiste una barra laterale.
    """
    return Rect(
        x=rect.x + USABLE_LEFT, y=rect.y + USABLE_TOP, w=rect.w, h=rect.h
    )
