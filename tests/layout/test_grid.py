"""Test della griglia."""
from __future__ import annotations

import pytest

from custom_components.switchbot_eink.layout.const import (
    GRID_COLS,
    GRID_ROWS,
    USABLE_HEIGHT,
    USABLE_WIDTH,
)
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


def test_ogni_coppia_di_colonne_adiacenti_dista_una_gutter() -> None:
    for col in range(GRID_COLS - 1):
        sinistra = grid_to_rect(col, 0, 1, 1)
        destra = grid_to_rect(col + 1, 0, 1, 1)

        assert destra.x - (sinistra.x + sinistra.w) == 8, f"fra colonna {col} e {col + 1}"


def test_ogni_coppia_di_righe_adiacenti_dista_una_gutter() -> None:
    for row in range(GRID_ROWS - 1):
        sopra = grid_to_rect(0, row, 1, 1)
        sotto = grid_to_rect(0, row + 1, 1, 1)

        assert sotto.y - (sopra.y + sopra.h) == 8, f"fra riga {row} e {row + 1}"


def test_nessuna_combinazione_esce_dall_area_utile() -> None:
    for col in range(GRID_COLS):
        for span_w in range(1, GRID_COLS - col + 1):
            for row in range(GRID_ROWS):
                for span_h in range(1, GRID_ROWS - row + 1):
                    rect = grid_to_rect(col, row, span_w, span_h)

                    assert rect_fits(rect), f"{col},{row},{span_w},{span_h} produce {rect}"


def test_due_celle_distinte_non_si_sovrappongono_mai() -> None:
    celle = [grid_to_rect(col, row, 1, 1) for col in range(GRID_COLS) for row in range(GRID_ROWS)]

    for indice, una in enumerate(celle):
        for altra in celle[indice + 1 :]:
            assert not rects_overlap(una, altra), f"{una} e {altra}"


def test_uno_span_copre_esattamente_le_celle_che_attraversa() -> None:
    for col in range(GRID_COLS):
        for span_w in range(1, GRID_COLS - col + 1):
            span = grid_to_rect(col, 0, span_w, 1)
            prima = grid_to_rect(col, 0, 1, 1)
            ultima = grid_to_rect(col + span_w - 1, 0, 1, 1)

            assert span.x == prima.x, f"span da {col} largo {span_w}"
            assert span.x + span.w == ultima.x + ultima.w, f"span da {col} largo {span_w}"
