"""Griglia 12×6 sull'area utile del pannello."""
from __future__ import annotations

from dataclasses import dataclass

from .const import (
    DEFAULT_GUTTER,
    GRID_COLS,
    GRID_ROWS,
    USABLE_HEIGHT,
    USABLE_WIDTH,
)


@dataclass(frozen=True, slots=True)
class Rect:
    """Un rettangolo in pixel sull'area utile."""

    x: int
    y: int
    w: int
    h: int


def grid_to_rect(
    col: int, row: int, span_w: int, span_h: int, gutter: int = DEFAULT_GUTTER
) -> Rect:
    """Converte una posizione di griglia in pixel.

    Le celle hanno dimensione frazionaria; arrotondiamo solo alla fine così che
    span adiacenti restino allineati e uno span pieno copra esattamente l'area.
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

    cell_w = (USABLE_WIDTH - gutter * (GRID_COLS - 1)) / GRID_COLS
    cell_h = (USABLE_HEIGHT - gutter * (GRID_ROWS - 1)) / GRID_ROWS

    return Rect(
        x=round(col * (cell_w + gutter)),
        y=round(row * (cell_h + gutter)),
        w=round(span_w * cell_w + (span_w - 1) * gutter),
        h=round(span_h * cell_h + (span_h - 1) * gutter),
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
