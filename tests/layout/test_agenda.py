"""Test del generatore dell'agenda."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from custom_components.switchbot_eink.layout.agenda import (
    CHAR_WIDTH_RATIO,
    FINESTRA_GIORNI,
    MAX_EVENTI_OGGI,
    Event,
    build_agenda_page,
    calendar_markers,
    truncate,
)
from custom_components.switchbot_eink.layout.compile import compile_page
from custom_components.switchbot_eink.layout.schema import validate_page

ADESSO = datetime(2026, 8, 23, 17, 24)


def evento(ora: int, titolo: str, calendario: str = "Personale", giorno: int = 0,
           all_day: bool = False) -> Event:
    inizio = ADESSO.replace(hour=ora, minute=0) + timedelta(days=giorno)
    return Event(
        start=inizio,
        end=inizio + timedelta(hours=1),
        summary=titolo,
        all_day=all_day,
        calendar=calendario,
    )


def test_un_solo_calendario_non_ha_bisogno_di_marcatori() -> None:
    assert calendar_markers(["Personale"]) == {"Personale": "P"}


def test_due_calendari_diversi_prendono_liniziale() -> None:
    assert calendar_markers(["Lavoro", "Famiglia"]) == {"Lavoro": "L", "Famiglia": "F"}


def test_liniziale_condivisa_si_estende_a_due_lettere() -> None:
    marcatori = calendar_markers(["Lavoro", "Ludoteca"])

    assert marcatori["Lavoro"] == "L"
    assert marcatori["Ludoteca"] == "LU"


def test_lambiguita_residua_ripiega_su_una_cifra() -> None:
    marcatori = calendar_markers(["Lavoro", "La", "Lavanderia"])

    assert len(set(marcatori.values())) == 3
    assert all(len(m) <= 2 for m in marcatori.values())


def test_i_marcatori_sono_deterministici() -> None:
    nomi = ["Lavoro", "Ludoteca", "Famiglia"]

    assert calendar_markers(nomi) == calendar_markers(nomi)


def test_un_testo_corto_non_viene_toccato() -> None:
    assert truncate("Palestra", 464, 22) == "Palestra"


def test_un_testo_lungo_viene_chiuso_da_unellissi() -> None:
    lungo = "Riunione di allineamento trimestrale con tutto il reparto"
    tagliato = truncate(lungo, 464, 22)

    assert tagliato.endswith("…")
    assert len(tagliato) < len(lungo)


def test_il_troncamento_lascia_almeno_un_carattere() -> None:
    """Un rettangolo assurdo non deve produrre una stringa vuota o un errore."""
    assert truncate("Palestra", 4, 22) != ""


def test_un_corpo_piu_grande_lascia_meno_caratteri() -> None:
    lungo = "x" * 200

    assert len(truncate(lungo, 464, 30)) < len(truncate(lungo, 464, 16))


def testi_di(page: dict) -> list[str]:
    return [c["text"] for c in page["cards"] if c["type"] == "text"]


# Il prefisso "test" di pytest e' senza underscore: senza questo, l'helper
# verrebbe raccolto come un test vero e fallirebbe per assenza della fixture
# `page`.
testi_di.__test__ = False  # type: ignore[attr-defined]


def test_la_pagina_generata_e_valida_e_compilabile() -> None:
    """Il generatore non e' un percorso parallelo: produce quello che lo schema
    valida e che il compilatore sa gia' tradurre."""
    page = build_agenda_page([evento(9, "Riunione")], ADESSO)

    validata = validate_page(page)
    componenti = compile_page(validata, lambda t: t, lambda _e: None)

    assert componenti


def test_la_pagina_finisce_sulla_home() -> None:
    assert build_agenda_page([], ADESSO)["page"] == "home"


def test_lintestazione_nomina_il_giorno_di_oggi() -> None:
    testi = testi_di(build_agenda_page([evento(9, "Riunione")], ADESSO))

    # 23 agosto 2026 e' una domenica sul calendario gregoriano reale.
    assert any("OGGI" in t and "domenica 23 agosto" in t for t in testi)


def test_gli_eventi_di_oggi_compaiono_con_ora_e_titolo() -> None:
    testi = testi_di(build_agenda_page([evento(9, "Riunione")], ADESSO))

    assert "09:00" in testi
    assert "Riunione" in testi


def test_gli_eventi_di_oggi_sono_in_ordine_di_ora() -> None:
    page = build_agenda_page(
        [evento(18, "Palestra"), evento(9, "Riunione"), evento(13, "Pranzo")], ADESSO
    )
    testi = testi_di(page)

    assert testi.index("09:00") < testi.index("13:00") < testi.index("18:00")


def test_un_evento_di_tutto_il_giorno_non_mostra_unora_finta() -> None:
    page = build_agenda_page([evento(0, "Ferie", all_day=True)], ADESSO)
    testi = testi_di(page)

    assert "00:00" not in testi
    assert any("Tutto il giorno" in t and "Ferie" in t for t in testi)


def test_gli_eventi_oltre_il_massimo_diventano_una_riga_di_riepilogo() -> None:
    """Far sparire eventi in silenzio e' peggio che dire quanti ne mancano."""
    eventi = [evento(8 + i, f"Evento {i}") for i in range(MAX_EVENTI_OGGI + 3)]
    testi = testi_di(build_agenda_page(eventi, ADESSO))

    assert "+3 altri" in testi
    assert f"Evento {MAX_EVENTI_OGGI + 2}" not in testi


def test_esattamente_il_massimo_non_produce_la_riga_di_riepilogo() -> None:
    eventi = [evento(8 + i, f"Evento {i}") for i in range(MAX_EVENTI_OGGI)]
    testi = testi_di(build_agenda_page(eventi, ADESSO))

    assert not any(t.startswith("+") and t.endswith("altri") for t in testi)


def test_i_giorni_successivi_stanno_su_una_riga_ciascuno() -> None:
    page = build_agenda_page(
        [evento(9, "Dentista", giorno=1), evento(10, "Call", giorno=2)], ADESSO
    )
    testi = testi_di(page)

    # 24 agosto 2026 e' lunedi, 25 agosto e' martedi.
    assert any(t.startswith("LUN 24") and "Dentista" in t for t in testi)
    assert any(t.startswith("MAR 25") and "Call" in t for t in testi)


def test_la_finestra_scarta_quello_che_cade_oltre() -> None:
    testi = testi_di(
        build_agenda_page([evento(9, "Troppo in la", giorno=FINESTRA_GIORNI)], ADESSO)
    )

    assert not any("Troppo in la" in t for t in testi)


def test_lagenda_vuota_lo_dice_invece_di_sembrare_rotta() -> None:
    testi = testi_di(build_agenda_page([], ADESSO))

    assert any("Nessun evento" in t for t in testi)


def test_lora_di_aggiornamento_e_sempre_presente() -> None:
    """Il pannello legge ogni tre ore: senza questa riga chi guarda non puo'
    distinguere un'agenda fresca da una di stamattina."""
    for eventi in ([], [evento(9, "Riunione")]):
        testi = testi_di(build_agenda_page(eventi, ADESSO))

        assert "agg. 17:24" in testi


def test_con_un_solo_calendario_non_compaiono_marcatori() -> None:
    page = build_agenda_page([evento(9, "Riunione")], ADESSO, calendars=["Personale"])

    assert "P" not in testi_di(page)


def test_con_piu_calendari_ogni_evento_porta_il_suo_marcatore() -> None:
    page = build_agenda_page(
        [evento(9, "Riunione", "Lavoro"), evento(18, "Cena", "Famiglia")],
        ADESSO,
        calendars=["Lavoro", "Famiglia"],
    )
    testi = testi_di(page)

    assert "L" in testi
    assert "F" in testi


def test_i_marcatori_dipendono_dai_calendari_scelti_non_da_quelli_con_eventi() -> None:
    """Se un calendario oggi e' vuoto, i marcatori degli altri non devono
    sparire: l'utente ne ha scelti due e si aspetta di distinguerli."""
    page = build_agenda_page(
        [evento(9, "Riunione", "Lavoro")], ADESSO, calendars=["Lavoro", "Famiglia"]
    )

    assert "L" in testi_di(page)


def test_nessuna_card_esce_dallarea_utile() -> None:
    eventi = [evento(8 + i, "x" * 200) for i in range(MAX_EVENTI_OGGI + 2)]
    page = validate_page(build_agenda_page(eventi, ADESSO, calendars=["A", "B"]))

    for card in page["cards"]:
        x, y, w, h = card["position"]
        assert 0 <= x and 0 <= y
        assert x + w <= 560
        assert y + h <= 380


def test_i_titoli_non_passano_dal_motore_di_template() -> None:
    """Un evento intitolato con delle graffe arriva da un invito esterno: va
    mostrato, non eseguito."""
    page = build_agenda_page([evento(9, "Riunione {{ 1 + 1 }}")], ADESSO)

    assert all(c.get("template") is False for c in page["cards"] if c["type"] == "text")

    componenti = compile_page(
        validate_page(page), lambda _t: "ESEGUITO", lambda _e: None
    )
    testi = [json.loads(c["extra"])["content"].get("text") for c in componenti]

    assert "ESEGUITO" not in testi
