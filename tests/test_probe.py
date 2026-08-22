"""Test del costruttore di componenti della sonda."""
from __future__ import annotations

import json

import pytest

from tools.probe import build_clock_component, read_credentials


def test_build_clock_component_produce_css_ed_extra_come_stringhe() -> None:
    component = build_clock_component("12:34:56")

    assert isinstance(component["css"], str)
    assert isinstance(component["extra"], str)


def test_build_clock_component_ha_id_numerico_valido() -> None:
    component = build_clock_component("12:34:56")

    assert component["id"] == "1"
    assert component["id"].isdigit()


def test_build_clock_component_posiziona_in_alto_a_sinistra() -> None:
    css = json.loads(build_clock_component("12:34:56")["css"])

    assert css["x"] == 0
    assert css["y"] == 0
    assert css["w"] == 800


def test_build_clock_component_contiene_il_testo() -> None:
    extra = json.loads(build_clock_component("12:34:56")["extra"])

    assert extra["content"]["text"] == "12:34:56"
    assert extra["source"] == "custom"
    assert extra["dataMode"] == "text"


def test_credenziali_mancanti_spiegano_cosa_impostare(monkeypatch) -> None:
    monkeypatch.delenv("SWITCHBOT_USER", raising=False)
    monkeypatch.setenv("SWITCHBOT_PASS", "segreta")

    with pytest.raises(SystemExit) as errore:
        read_credentials()

    assert "SWITCHBOT_USER" in str(errore.value)


def test_regione_non_valida_viene_rifiutata_subito(monkeypatch) -> None:
    monkeypatch.setenv("SWITCHBOT_USER", "mario@example.test")
    monkeypatch.setenv("SWITCHBOT_PASS", "segreta")
    monkeypatch.setenv("SWITCHBOT_REGION", "italia")

    with pytest.raises(SystemExit) as errore:
        read_credentials()

    assert "SWITCHBOT_REGION" in str(errore.value)


def test_la_regione_viene_normalizzata(monkeypatch) -> None:
    monkeypatch.setenv("SWITCHBOT_USER", "mario@example.test")
    monkeypatch.setenv("SWITCHBOT_PASS", "segreta")
    monkeypatch.setenv("SWITCHBOT_REGION", " EU ")

    _username, _password, regione = read_credentials()

    assert regione == "eu"
