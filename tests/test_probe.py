"""Test del costruttore di componenti della sonda."""
from __future__ import annotations

import json

import pytest

from custom_components.switchbot_eink.api.models import TemplateSummary
from tools.probe import (
    build_clock_component,
    build_frame_components,
    build_ruler_components,
    read_credentials,
    templates_to_wipe,
)


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


def _sommario(template_id: int, slot: str) -> TemplateSummary:
    return TemplateSummary(
        template_id=template_id,
        name="x",
        page_slot=slot,
        template_type=1 if slot == "home" else 0,
    )


def test_il_wipe_non_tocca_mai_la_home() -> None:
    """La home non si cancella, si sovrascrive: senza template home non
    sappiamo cosa mostri il pannello all'accensione."""
    tutti = [
        _sommario(1105, "home"),
        _sommario(580, "custom1"),
        _sommario(1316, "custom2"),
    ]

    assert [s.template_id for s in templates_to_wipe(tutti)] == [580, 1316]


def test_il_wipe_di_un_pannello_gia_pulito_non_cancella_niente() -> None:
    assert templates_to_wipe([_sommario(1105, "home")]) == []


def test_il_righello_etichetta_ogni_tacca_con_la_sua_coordinata() -> None:
    componenti = build_ruler_components([240], [370])
    css = [json.loads(c["css"]) for c in componenti]
    testi = [json.loads(c["extra"])["content"]["text"] for c in componenti]

    assert testi == ["x240", "y370"]
    assert css[0]["x"] == 240
    assert css[1]["y"] == 370


def test_il_righello_sfalsa_le_etichette_per_non_sovrapporle() -> None:
    """Con passi da 10 px le caselle larghe 76 colliderebbero: le tacche
    dell'asse x scalano in verticale, quelle dell'asse y in orizzontale."""
    componenti = build_ruler_components([200, 210, 220], [370, 380, 390])
    css = [json.loads(c["css"]) for c in componenti]

    assert len({c["y"] for c in css[:3]}) == 3
    assert len({c["x"] for c in css[3:]}) == 3


def test_il_telaio_mette_gli_angoli_dentro_il_rettangolo() -> None:
    componenti = build_frame_components(240, 0, 800, 380)
    css = [json.loads(c["css"]) for c in componenti]

    assert all(c["x"] >= 240 and c["y"] >= 0 for c in css)
    assert all(c["x"] + c["w"] <= 800 and c["y"] + c["h"] <= 380 for c in css)


def test_gli_identificativi_dei_componenti_sono_unici_e_numerici() -> None:
    """Un id non numerico viene serializzato come 0 e tutti i componenti
    collidono su quello: e' gia' successo in questo progetto."""
    for componenti in (
        build_ruler_components([0, 40], [0, 40]),
        build_frame_components(240, 0, 800, 380),
    ):
        identificativi = [c["id"] for c in componenti]
        assert all(i.isdigit() and int(i) > 0 for i in identificativi)
        assert len(set(identificativi)) == len(identificativi)
