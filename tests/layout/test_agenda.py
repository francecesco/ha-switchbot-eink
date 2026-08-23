"""Test del generatore dell'agenda."""
from __future__ import annotations

import itertools
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
from custom_components.switchbot_eink.layout.grid import Rect, rect_fits, rects_overlap
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


def evento_attivo(minuti_da_ora: int, titolo: str, calendario: str = "Personale") -> Event:
    """Un evento che inizia `minuti_da_ora` minuti dopo ADESSO e dura un'ora.

    Serve per gli scenari con molti eventi nella lista di oggi: ADESSO e' alle
    17:24, quindi eventi ancorati a un'ora del giorno fissa (le 8, le 9, ...)
    cadrebbero nel passato e il filtro sugli eventi conclusi li farebbe sparire,
    svuotando lo stress test invece di stressarlo.
    """
    inizio = ADESSO + timedelta(minutes=minuti_da_ora)
    return Event(
        start=inizio,
        end=inizio + timedelta(minutes=60),
        summary=titolo,
        all_day=False,
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


def test_i_nomi_di_calendario_duplicati_non_sprecano_un_marcatore() -> None:
    """Senza una deduplicazione a monte, la seconda occorrenza di "Lavoro" si
    contende "L" e "LA" con la prima e una delle due lettere resta inutilizzata."""
    marcatori = calendar_markers(["Lavoro", "Lavoro", "Famiglia"])

    assert marcatori == {"Lavoro": "L", "Famiglia": "F"}


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


def test_lellissi_rientra_nel_budget_di_caratteri() -> None:
    massimo = int(464 / (CHAR_WIDTH_RATIO * 22))
    tagliato = truncate("x" * 200, 464, 22)

    assert len(tagliato) <= massimo


def test_lo_spazio_prima_dellellissi_non_resta() -> None:
    massimo = int(464 / (CHAR_WIDTH_RATIO * 22))
    testo = "A" * (massimo - 2) + " " + "B" * 50
    tagliato = truncate(testo, 464, 22)

    assert not tagliato.removesuffix("…").endswith(" ")


def testi_di(page: dict) -> list[str]:
    return [c["text"] for c in page["cards"] if c["type"] == "text"]


# Il prefisso "test" di pytest e' senza underscore: senza questo, l'helper
# verrebbe raccolto come un test vero e fallirebbe per assenza della fixture
# `page`.
testi_di.__test__ = False  # type: ignore[attr-defined]


def test_la_pagina_generata_e_valida_e_compilabile() -> None:
    """Il generatore non e' un percorso parallelo: produce quello che lo schema
    valida e che il compilatore sa gia' tradurre."""
    page = build_agenda_page([evento(20, "Riunione")], ADESSO)

    validata = validate_page(page)
    componenti = compile_page(validata, lambda t: t, lambda _e: None)

    assert componenti


def test_la_pagina_finisce_sulla_home() -> None:
    assert build_agenda_page([], ADESSO)["page"] == "home"


def test_lintestazione_nomina_il_giorno_di_oggi() -> None:
    testi = testi_di(build_agenda_page([evento(20, "Riunione")], ADESSO))

    # 23 agosto 2026 e' una domenica sul calendario gregoriano reale.
    assert any("OGGI" in t and "domenica 23 agosto" in t for t in testi)


def test_gli_eventi_di_oggi_compaiono_con_ora_e_titolo() -> None:
    """ADESSO e' alle 17:24: l'evento deve finire dopo per non essere concluso."""
    testi = testi_di(build_agenda_page([evento(20, "Riunione")], ADESSO))

    assert "20:00" in testi
    assert "Riunione" in testi


def test_gli_eventi_di_oggi_sono_in_ordine_di_ora() -> None:
    page = build_agenda_page(
        [evento(22, "Palestra"), evento(18, "Riunione"), evento(20, "Pranzo")], ADESSO
    )
    testi = testi_di(page)

    assert testi.index("18:00") < testi.index("20:00") < testi.index("22:00")


def test_un_evento_di_tutto_il_giorno_non_mostra_unora_finta() -> None:
    page = build_agenda_page([evento(0, "Ferie", all_day=True)], ADESSO)
    testi = testi_di(page)

    assert "00:00" not in testi
    assert any("Tutto il giorno" in t and "Ferie" in t for t in testi)


def test_un_evento_di_tutto_il_giorno_non_emette_una_card_vuota() -> None:
    """Senza questo, un evento di tutto il giorno oggi produce un rettangolo di
    72 px senza niente dentro."""
    page = build_agenda_page([evento(0, "Ferie", all_day=True)], ADESSO)

    assert not any(c["text"] == "" for c in page["cards"] if c["type"] == "text")


def test_gli_eventi_oltre_il_massimo_diventano_una_riga_di_riepilogo() -> None:
    """Far sparire eventi in silenzio e' peggio che dire quanti ne mancano."""
    eventi = [evento_attivo(10 * i, f"Evento {i}") for i in range(MAX_EVENTI_OGGI + 3)]
    testi = testi_di(build_agenda_page(eventi, ADESSO))

    assert "+3 altri" in testi
    assert f"Evento {MAX_EVENTI_OGGI + 2}" not in testi


def test_esattamente_il_massimo_non_produce_la_riga_di_riepilogo() -> None:
    eventi = [evento_attivo(10 * i, f"Evento {i}") for i in range(MAX_EVENTI_OGGI)]
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
    for eventi in ([], [evento(20, "Riunione")]):
        testi = testi_di(build_agenda_page(eventi, ADESSO))

        assert "agg. 17:24" in testi


def test_stamp_false_omette_lora_di_aggiornamento() -> None:
    """Chi confronta due pagine per decidere se ripubblicare deve poter
    escludere l'orario: altrimenti cambia ad ogni minuto e il confronto e'
    inutile."""
    for eventi in ([], [evento(20, "Riunione")]):
        testi = testi_di(build_agenda_page(eventi, ADESSO, stamp=False))

        assert not any(t.startswith("agg. ") for t in testi)


def test_con_un_solo_calendario_non_compaiono_marcatori() -> None:
    page = build_agenda_page([evento(20, "Riunione")], ADESSO, calendars=["Personale"])

    assert "P" not in testi_di(page)


def test_con_piu_calendari_ogni_evento_porta_il_suo_marcatore() -> None:
    page = build_agenda_page(
        [evento(19, "Riunione", "Lavoro"), evento(18, "Cena", "Famiglia")],
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
        [evento(20, "Riunione", "Lavoro")], ADESSO, calendars=["Lavoro", "Famiglia"]
    )

    assert "L" in testi_di(page)


def test_un_calendario_non_elencato_prende_un_marcatore_visibile() -> None:
    """Un marcatore vuoto e silenzioso nasconde il problema; "?" lo segnala."""
    page = build_agenda_page(
        [evento(20, "Riunione", "Sconosciuto")], ADESSO, calendars=["Lavoro", "Famiglia"]
    )

    assert "?" in testi_di(page)


def test_la_riga_dei_marcatori_rispetta_la_nuova_geometria() -> None:
    """_LARGHEZZA_MARCATORE=12 con corpo 18 non contiene due caratteri come
    "LU": la tabella del capitolato allarga la colonna e sposta ora/titolo."""
    page = build_agenda_page(
        [evento(18, "Riunione", "Lavoro")], ADESSO, calendars=["Lavoro", "Ludoteca"]
    )
    testuali = [c for c in page["cards"] if c["type"] == "text"]
    marcatore = next(c for c in testuali if c["text"] == "L")
    ora = next(c for c in testuali if c["text"] == "18:00")
    titolo = next(c for c in testuali if c["text"] == "Riunione")

    assert marcatore["position"][2] == 20
    assert marcatore["style"]["fontSize"] == 14
    assert ora["position"][0] == 24
    assert titolo["position"][0] == 104
    assert titolo["position"][2] == 456


def test_i_titoli_non_passano_dal_motore_di_template() -> None:
    """Un evento intitolato con delle graffe arriva da un invito esterno: va
    mostrato, non eseguito."""
    page = build_agenda_page([evento(20, "Riunione {{ 1 + 1 }}")], ADESSO)

    assert all(c.get("template") is False for c in page["cards"] if c["type"] == "text")

    componenti = compile_page(
        validate_page(page), lambda _t: "ESEGUITO", lambda _e: None
    )
    testi = [json.loads(c["extra"])["content"].get("text") for c in componenti]

    assert "ESEGUITO" not in testi


def test_un_evento_gia_in_corso_compare_lo_stesso() -> None:
    """Una settimana di ferie cominciata lunedi' deve vedersi anche il mercoledi'."""
    ferie = Event(
        start=ADESSO.replace(hour=0, minute=0) - timedelta(days=3),
        end=ADESSO.replace(hour=0, minute=0) + timedelta(days=4),
        summary="Ferie",
        all_day=True,
        calendar="Personale",
    )
    testi = testi_di(build_agenda_page([ferie], ADESSO))

    assert any("Ferie" in t for t in testi)


def test_un_evento_a_cavallo_della_mezzanotte_compare_oggi() -> None:
    """L'evento e' cominciato ieri sera e non e' ancora finito adesso (17:24):
    non ha un'ora d'inizio sensata da mostrare oggi."""
    notturno = Event(
        start=ADESSO.replace(hour=22, minute=0) - timedelta(days=1),
        end=ADESSO.replace(hour=20, minute=0),
        summary="Turno di notte",
        all_day=False,
        calendar="Personale",
    )
    testi = testi_di(build_agenda_page([notturno], ADESSO))

    assert any("In corso" in t and "Turno di notte" in t for t in testi)


def test_un_evento_che_finisce_a_mezzanotte_non_occupa_il_giorno_dopo() -> None:
    fino_a_mezzanotte = Event(
        start=ADESSO.replace(hour=20, minute=0),
        end=ADESSO.replace(hour=0, minute=0) + timedelta(days=1),
        summary="Serata",
        all_day=False,
        calendar="Personale",
    )
    page = build_agenda_page([fino_a_mezzanotte], ADESSO)
    riga_domani = next(t for t in testi_di(page) if t.startswith("LUN 24"))

    assert "Serata" not in riga_domani


def test_la_pagina_non_dipende_dallordine_in_cui_arrivano_gli_eventi() -> None:
    """Senza una chiave d'ordinamento totale, due eventi alla stessa ora si
    scambiano a seconda di come il backend li restituisce, l'hash cambia, e il
    pannello viene ripubblicato senza motivo."""
    eventi = [
        evento(18, "Beta"), evento(18, "Alfa"),
        evento(18, "Gamma", "Lavoro"), evento(20, "Delta"),
    ]
    attesa = build_agenda_page(eventi, ADESSO)

    for permutazione in itertools.permutations(eventi):
        assert build_agenda_page(list(permutazione), ADESSO) == attesa


def test_gli_eventi_gia_conclusi_non_occupano_le_righe_di_oggi() -> None:
    conclusi = [evento(8 + i, f"Passato {i}") for i in range(MAX_EVENTI_OGGI)]
    futuro = evento(21, "Cena")
    testi = testi_di(build_agenda_page([*conclusi, futuro], ADESSO))

    assert "Cena" in testi
    assert "Passato 0" not in testi


def test_una_giornata_tutta_conclusa_lo_dice() -> None:
    testi = testi_di(build_agenda_page([evento(8, "Colazione")], ADESSO))

    assert any("Nessun altro evento oggi" in t for t in testi)


def test_oggi_vuoto_con_i_giorni_dopo_pieni_non_lascia_il_bianco() -> None:
    testi = testi_di(build_agenda_page([evento(9, "Dentista", giorno=1)], ADESSO))

    assert any("Nessun evento oggi" in t for t in testi)
    assert any("Dentista" in t for t in testi)


def _pagine_estreme() -> list[dict]:
    """Le forme che stressano l'impaginazione, una per riga di rischio."""
    lungo = "Riunione di allineamento trimestrale con tutto il reparto e ospiti"
    # Eventi ancorati a un minutaggio relativo ad ADESSO, non a un'ora fissa
    # del giorno: cosi' restano tutti "attivi" indipendentemente da che ore
    # sono in ADESSO, e lo stress test stressa davvero il massimo per riga.
    pieni = [evento_attivo(10 * i, f"{lungo} {i}") for i in range(MAX_EVENTI_OGGI + 4)]
    return [
        build_agenda_page([], ADESSO),
        # Attivo, non alle 9: con ADESSO alle 17:24 un evento del mattino e' gia'
        # concluso e la forma collasserebbe nel segnaposto, senza mai esercitare
        # la geometria di una riga singola.
        build_agenda_page([evento_attivo(30, "x")], ADESSO),
        build_agenda_page(pieni, ADESSO),
        build_agenda_page(pieni, ADESSO, calendars=["Lavoro", "Famiglia"]),
        build_agenda_page(
            [evento(0, lungo, all_day=True), *pieni],
            ADESSO,
            calendars=["Lavoro", "Famiglia", "Ludoteca"],
        ),
        build_agenda_page(
            [evento(9, lungo, giorno=1), evento(10, lungo, giorno=2)], ADESSO
        ),
        build_agenda_page(
            [evento(9, lungo, giorno=1)] * 6 + [evento(9, lungo, giorno=2)] * 6,
            ADESSO,
        ),
    ]


@pytest.mark.parametrize("indice", range(7))
def test_nessuna_card_esce_dallarea_utile_in_nessuna_forma(indice: int) -> None:
    page = validate_page(_pagine_estreme()[indice])

    for posizione, card in enumerate(page["cards"]):
        x, y, w, h = card["position"]
        assert rect_fits(Rect(x, y, w, h)), f"card {posizione} fuori: {card}"


@pytest.mark.parametrize("indice", range(7))
def test_nessuna_coppia_di_card_si_sovrappone(indice: int) -> None:
    """Il compilatore rifiuta le sovrapposizioni: una geometria sbagliata non
    degrada la pagina, la fa sparire."""
    page = validate_page(_pagine_estreme()[indice])
    rettangoli = [Rect(*card["position"]) for card in page["cards"]]

    for primo in range(len(rettangoli)):
        for secondo in range(primo + 1, len(rettangoli)):
            assert not rects_overlap(rettangoli[primo], rettangoli[secondo]), (
                f"card {primo} e {secondo} si sovrappongono"
            )


@pytest.mark.parametrize("indice", range(7))
def test_ogni_forma_arriva_fino_ai_componenti(indice: int) -> None:
    componenti = compile_page(
        validate_page(_pagine_estreme()[indice]), lambda t: t, lambda _e: None
    )

    assert componenti
