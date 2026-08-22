"""Test della serializzazione nel wire format."""
from __future__ import annotations

import json

import pytest

from custom_components.switchbot_eink.layout.grid import Rect
from custom_components.switchbot_eink.layout.widgets import to_wire, validate_component_id

RECT = Rect(10, 20, 200, 80)


def test_css_ed_extra_sono_stringhe_json() -> None:
    wire = to_wire("1", "text", "Titolo", RECT, {"text": "ciao"})

    assert isinstance(wire["css"], str)
    assert isinstance(wire["extra"], str)
    json.loads(wire["css"])
    json.loads(wire["extra"])


def test_css_contiene_la_geometria() -> None:
    css = json.loads(to_wire("1", "text", "Titolo", RECT, {"text": "ciao"})["css"])

    assert css["x"] == 10
    assert css["y"] == 20
    assert css["w"] == 200
    assert css["h"] == 80
    assert css["z"] == 1


def test_extra_contiene_data_content_e_flag() -> None:
    extra = json.loads(to_wire("1", "text", "Titolo", RECT, {"text": "ciao"})["extra"])

    assert extra["dataMode"] == "text"
    assert extra["source"] == "custom"
    assert extra["refresh"] == "1h"
    assert extra["content"] == {"text": "ciao"}
    assert extra["locked"] is False
    assert extra["visible"] is True


def test_lo_stile_di_text_e_filtrato_dalla_whitelist() -> None:
    css = json.loads(
        to_wire(
            "1",
            "text",
            "Titolo",
            RECT,
            {"text": "ciao"},
            style={"fontSize": 24, "padding": 12, "radius": 4},
        )["css"]
    )

    assert css["fontSize"] == 24
    assert "padding" not in css, "padding non è nella whitelist di text"
    assert "radius" not in css


def test_un_tipo_senza_whitelist_conserva_tutto_lo_stile() -> None:
    css = json.loads(
        to_wire(
            "1",
            "switchbotMeter",
            "Tile",
            RECT,
            {"label": "Salotto", "value": "21", "unit": "°C"},
            style={"padding": 12, "iconSize": 48},
        )["css"]
    )

    assert css["padding"] == 12
    assert css["iconSize"] == 48


def test_i_default_di_stile_si_applicano_prima_della_whitelist() -> None:
    css = json.loads(to_wire("1", "weekday", "Giorno", RECT, {})["css"])

    assert css["fontSize"] == 16


def test_lo_stile_esplicito_vince_sul_default() -> None:
    css = json.loads(to_wire("1", "weekday", "Giorno", RECT, {}, style={"fontSize": 32})["css"])

    assert css["fontSize"] == 32


def test_il_content_delle_tile_metric_e_filtrato() -> None:
    extra = json.loads(
        to_wire(
            "1",
            "switchbotMeter",
            "Tile",
            RECT,
            {"icon": "gauge", "label": "L", "value": "V", "unit": "U", "extraneo": "x"},
        )["extra"]
    )

    assert extra["content"] == {"icon": "gauge", "label": "L", "value": "V", "unit": "U"}


def test_il_content_filtrato_omette_le_chiavi_assenti() -> None:
    extra = json.loads(
        to_wire("1", "switchbotMeter", "Tile", RECT, {"label": "L", "value": "V"})["extra"]
    )

    assert extra["content"] == {"label": "L", "value": "V"}


def test_data_mode_e_configurabile() -> None:
    extra = json.loads(
        to_wire("1", "text", "T", RECT, {"text": "x"}, data_mode="clock")["extra"]
    )

    assert extra["dataMode"] == "clock"


def test_id_numerico_valido_passa() -> None:
    assert validate_component_id("42") == "42"


def test_id_non_numerico_solleva() -> None:
    with pytest.raises(ValueError, match="intero positivo"):
        validate_component_id("a1b2-uuid")


def test_id_zero_solleva() -> None:
    with pytest.raises(ValueError, match="intero positivo"):
        validate_component_id("0")


def test_id_oltre_il_massimo_solleva() -> None:
    with pytest.raises(ValueError, match="2147483647"):
        validate_component_id("2147483648")


def test_to_wire_rifiuta_un_id_non_valido() -> None:
    with pytest.raises(ValueError):
        to_wire("uuid-non-valido", "text", "T", RECT, {"text": "x"})
