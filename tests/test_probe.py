"""Test del costruttore di componenti della sonda."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from custom_components.switchbot_eink.api.models import TemplateSummary
from tools.probe import (
    build_agenda_components,
    build_clock_component,
    build_frame_components,
    build_ruler_components,
    read_credentials,
    sample_agenda_events,
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


def test_build_clock_component_posiziona_in_cima_allarea_utile() -> None:
    css = json.loads(build_clock_component("12:34:56")["css"])

    assert css["x"] == 240
    assert css["y"] == 0
    assert css["w"] == 560


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


def test_il_refresh_dellorologio_e_impostabile() -> None:
    """E' l'ipotesi in prova sulla cadenza: il valore deve arrivare al backend
    cosi' com'e', non essere riscritto a 1h."""
    extra = json.loads(build_clock_component("12:00:00", refresh="5m")["extra"])

    assert extra["refresh"] == "5m"


def test_lorologio_sta_a_destra_della_barra_laterale() -> None:
    css = json.loads(build_clock_component("12:00:00")["css"])

    assert css["x"] == 240
    assert css["x"] + css["w"] == 800


@pytest.mark.parametrize(
    "ora",
    [
        datetime(2026, 9, 28, 0, 5),
        datetime(2026, 9, 28, 9, 0),
        datetime(2026, 9, 28, 23, 50),
    ],
)
def test_lagenda_di_prova_compila_a_qualunque_ora(ora: datetime) -> None:
    """Gli eventi sono ancorati all'istante, quindi anche a mezzanotte meno
    dieci la pagina deve restare valida: niente card fuori area o sovrapposte."""
    componenti = build_agenda_components(ora)

    assert componenti
    identificativi = [c["id"] for c in componenti]
    assert len(set(identificativi)) == len(identificativi)
    for componente in componenti:
        css = json.loads(componente["css"])
        assert css["x"] >= 240
        assert css["x"] + css["w"] <= 800


def test_lagenda_di_prova_mostra_gli_eventi_di_oggi() -> None:
    ora = datetime(2026, 9, 28, 9, 0)
    testi = " ".join(
        json.dumps(json.loads(c["extra"])["content"], ensure_ascii=False)
        for c in build_agenda_components(ora)
    )

    assert "Evento in corso" in testi
    assert "Riunione settimanale" in testi
    # Oggi ce ne sono otto: cinque righe, e gli altri dichiarati, non spariti.
    assert "+3 altri" in testi
    assert "DOMANI" in testi
    assert "Dentista" in testi


def test_gli_eventi_di_prova_coprono_i_tre_giorni_e_due_calendari() -> None:
    ora = datetime(2026, 9, 28, 9, 0)
    eventi = sample_agenda_events(ora)

    giorni = {e.start.date() for e in eventi}
    assert {ora.date() + timedelta(days=n) for n in range(3)} <= giorni
    assert len({e.calendar for e in eventi}) >= 2
    assert any(e.all_day for e in eventi)
    assert any(e.start < ora < e.end for e in eventi)


def test_lagenda_di_prova_si_puo_vedere_in_inglese() -> None:
    ora = datetime(2026, 9, 28, 9, 0)
    testi = " ".join(
        json.dumps(json.loads(c["extra"])["content"], ensure_ascii=False)
        for c in build_agenda_components(ora, language="en")
    )

    assert "TOMORROW" in testi
    assert "DOMANI" not in testi
