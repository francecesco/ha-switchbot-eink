"""Test della griglia."""
from __future__ import annotations

import pytest

from custom_components.switchbot_eink.layout.const import USABLE_HEIGHT, USABLE_WIDTH
from custom_components.switchbot_eink.layout.grid import (
    Rect,
    grid_to_rect,
    rect_fits,
    rects_overlap,
)


def test_prima_cella_parte_dall_origine() -> None:
    rect = grid_to_rect(0, 0, 1, 1)

    assert rect.x == 0
    assert rect.y == 0


def test_span_completo_riempie_l_area_utile() -> None:
    rect = grid_to_rect(0, 0, 12, 6)

    assert rect.w == USABLE_WIDTH
    assert rect.h == USABLE_HEIGHT


def test_tre_colonne_larghe_194_pixel() -> None:
    assert grid_to_rect(0, 0, 3, 1).w == 194


def test_la_quarta_colonna_inizia_dopo_la_gutter() -> None:
    prima = grid_to_rect(0, 0, 3, 1)
    seconda = grid_to_rect(3, 0, 3, 1)

    assert seconda.x == prima.x + prima.w + 8


def test_la_seconda_riga_inizia_dopo_la_gutter() -> None:
    prima = grid_to_rect(0, 0, 1, 1)
    seconda = grid_to_rect(0, 1, 1, 1)

    assert seconda.y == prima.y + prima.h + 8


def test_colonna_fuori_griglia_solleva() -> None:
    with pytest.raises(ValueError, match="colonna"):
        grid_to_rect(12, 0, 1, 1)


def test_span_che_esce_dalla_griglia_solleva() -> None:
    with pytest.raises(ValueError, match="larghezza"):
        grid_to_rect(10, 0, 3, 1)


def test_span_nullo_solleva() -> None:
    with pytest.raises(ValueError, match="almeno 1"):
        grid_to_rect(0, 0, 0, 1)


def test_rect_dentro_l_area_utile_ci_sta() -> None:
    assert rect_fits(Rect(0, 0, 800, 372)) is True


def test_rect_che_sborda_a_destra_non_ci_sta() -> None:
    assert rect_fits(Rect(700, 0, 200, 50)) is False


def test_rect_con_coordinate_negative_non_ci_sta() -> None:
    assert rect_fits(Rect(-1, 0, 100, 50)) is False


def test_rect_adiacenti_non_si_sovrappongono() -> None:
    assert rects_overlap(Rect(0, 0, 100, 50), Rect(100, 0, 100, 50)) is False


def test_rect_incrociati_si_sovrappongono() -> None:
    assert rects_overlap(Rect(0, 0, 100, 50), Rect(50, 20, 100, 50)) is True
