"""Genera la pagina dell'agenda dagli eventi dei calendari.

Non introduce un tipo di card nuovo: produce la stessa struttura che
`validate_page` valida e che `compile_page` traduce in componenti. Puro come il
resto dello strato: niente Home Assistant, niente `api/`.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from .const import USABLE_WIDTH

# Il pannello e' configurato in italiano — lo dichiara la risposta di `preview` —
# quindi i nomi stanno qui. Estrarli in un catalogo di lingue e' un problema per
# quando servira' la seconda lingua.
GIORNI: tuple[str, ...] = (
    "lunedi",
    "martedi",
    "mercoledi",
    "giovedi",
    "venerdi",
    "sabato",
    "domenica",
)
GIORNI_BREVI: tuple[str, ...] = ("LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM")
MESI: tuple[str, ...] = (
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
)

FINESTRA_GIORNI = 3
MAX_EVENTI_OGGI = 6

# Larghezza media di un carattere come frazione del corpo. E' una stima: i font
# del pannello non hanno spaziatura fissa e non ne abbiamo le metriche. Vive in
# un posto solo proprio perche' va tarata con una prova sul dispositivo.
CHAR_WIDTH_RATIO = 0.52

# Geometria, in coordinate dell'area utile (560 x 380).
_Y_INTESTAZIONE = 0
_Y_FILETTO_ALTO = 34
_Y_PRIMA_RIGA = 44
_ALTEZZA_RIGA = 34
_Y_RIEPILOGO = 248
_Y_FILETTO_BASSO = 278
_Y_PRIMO_GIORNO = 288
_ALTEZZA_RIGA_GIORNO = 30
_Y_AGGIORNAMENTO = 352

_CORPO_INTESTAZIONE = 24
_CORPO_EVENTO = 22
_CORPO_MARCATORE = 14
_CORPO_GIORNO = 16
_CORPO_AGGIORNAMENTO = 13

# Con corpo 18 e 12 px un marcatore a due lettere ("LU") non ci stava: la
# colonna e' piu' larga, e ora/titolo si spostano di conseguenza.
_LARGHEZZA_MARCATORE = 20
_LARGHEZZA_ORA = 72
_X_TITOLO_CON_MARCATORI = 104


@dataclass(frozen=True, slots=True)
class Event:
    """Un evento di calendario, senza tipi di Home Assistant."""

    start: datetime
    end: datetime
    summary: str
    all_day: bool
    calendar: str


def calendar_markers(names: Sequence[str]) -> dict[str, str]:
    """Un marcatore di al massimo due caratteri per ciascun calendario.

    Deterministico: iniziale maiuscola, estesa a due lettere in caso di
    collisione, e a una cifra progressiva se l'ambiguita' resta. Serve perche' il
    pannello offre solo `black` e `gray` come tonalita' di testo: distinguere i
    calendari col colore non e' possibile oltre i due.
    """
    marcatori: dict[str, str] = {}
    presi: set[str] = set()

    # Deduplicare prima di assegnare: senza questo, due occorrenze dello stesso
    # nome si contendono "L" e "LA" e una delle due lettere resta sprecata.
    for indice, nome in enumerate(dict.fromkeys(names)):
        pulito = nome.strip() or "?"
        candidato = next(
            (c for c in (pulito[0].upper(), pulito[:2].upper()) if c not in presi),
            None,
        )
        if candidato is None:
            contatore = indice + 1
            candidato = str(contatore)
            while candidato in presi:
                contatore += 1
                candidato = str(contatore)

        presi.add(candidato)
        marcatori[nome] = candidato

    return marcatori


def truncate(text: str, width_px: int, font_size: int) -> str:
    """Taglia il testo alla larghezza disponibile, chiudendolo con un'ellissi."""
    massimo = max(1, int(width_px / (CHAR_WIDTH_RATIO * font_size)))
    if len(text) <= massimo:
        return text
    return text[: max(1, massimo - 1)].rstrip() + "…"


def _card(
    testo: str,
    rettangolo: tuple[int, int, int, int],
    corpo: int,
    allineamento: str = "left",
) -> dict[str, Any]:
    x, y, larghezza, altezza = rettangolo
    return {
        "type": "text",
        "text": testo,
        # I titoli arrivano da inviti e calendari condivisi: dati che l'utente
        # non controlla. Eseguirli come Jinja sarebbe un'iniezione.
        "template": False,
        "position": [x, y, larghezza, altezza],
        "style": {"fontSize": corpo, "align": allineamento},
    }


def _filetto(y: int) -> dict[str, Any]:
    return {"type": "divider", "position": [0, y, USABLE_WIDTH, 2]}


def _intestazione(giorno: date) -> str:
    return f"OGGI · {GIORNI[giorno.weekday()]} {giorno.day} {MESI[giorno.month - 1]}"


def _copre(evento: Event, giorno: date) -> bool:
    """Vero se l'evento occupa almeno un istante del giorno.

    Raggruppare per `start.date()` faceva sparire tutto cio' che era gia' in
    corso: una settimana di ferie cominciata lunedi' non compariva il mercoledi'.
    """
    inizio = evento.start.date()
    fine = evento.end.date()
    # La fine e' esclusiva: Home Assistant mette il giorno *dopo* l'ultimo per gli
    # eventi di tutto il giorno, e un evento con orario che finisce a mezzanotte
    # non occupa il giorno seguente.
    if evento.end.time() == time.min and fine > inizio:
        fine -= timedelta(days=1)
    return inizio <= giorno <= fine


def _chiave_ordine(evento: Event, giorno: date) -> tuple[bool, datetime, str, str]:
    """Ordinamento totale: senza gli ultimi due campi due eventi alla stessa ora
    si scambiano a seconda di come il backend li restituisce, l'hash cambia, e il
    pannello viene ripubblicato senza motivo.
    """
    in_corso = evento.all_day or evento.start.date() < giorno
    return (not in_corso, evento.start, evento.summary, evento.calendar)


def _sintesi(evento: Event, giorno: date) -> str:
    if evento.all_day:
        return f"{evento.summary} (tutto il giorno)"
    if evento.start.date() < giorno:
        return f"In corso · {evento.summary}"
    return f"{evento.start.strftime('%H:%M')} {evento.summary}"


def _riga_giorno(giorno: date, eventi: Sequence[Event]) -> str:
    etichetta = f"{GIORNI_BREVI[giorno.weekday()]} {giorno.day}"
    if not eventi:
        return f"{etichetta}   nessun evento"
    return f"{etichetta}   " + " · ".join(_sintesi(e, giorno) for e in eventi)


def _per_giorno(
    events: Sequence[Event], giorni: Sequence[date]
) -> dict[date, list[Event]]:
    raggruppati: dict[date, list[Event]] = {}
    for giorno in giorni:
        # Un evento appartiene a un giorno se lo occupa, non se ci comincia.
        eventi_del_giorno = [evento for evento in events if _copre(evento, giorno)]
        eventi_del_giorno.sort(key=lambda e: _chiave_ordine(e, giorno))
        raggruppati[giorno] = eventi_del_giorno
    return raggruppati


def _titolo_riga_oggi(evento: Event, oggi: date) -> tuple[str, str]:
    """(ora, titolo) per la riga di un evento nella lista di oggi.

    Un evento in corso non ha un'ora d'inizio sensata da mostrare oggi: viene
    da un giorno precedente.
    """
    if evento.all_day:
        return "", f"Tutto il giorno · {evento.summary}"
    if evento.start.date() < oggi:
        return "", f"In corso · {evento.summary}"
    return evento.start.strftime("%H:%M"), evento.summary


def build_agenda_page(
    events: Sequence[Event],
    now: datetime,
    calendars: Sequence[str] | None = None,
    page_slot: str = "home",
    name: str = "Agenda",
    stamp: bool = True,
) -> dict[str, Any]:
    """Costruisce la definizione di pagina dell'agenda.

    `calendars` sono i calendari *scelti dall'utente*, non quelli che oggi hanno
    eventi: i marcatori non devono sparire quando un calendario e' vuoto.

    `stamp=False` omette la card "agg. HH:MM": chi confronta due pagine per
    decidere se ripubblicare deve poter escludere l'orario, altrimenti cambia
    ad ogni minuto e il confronto non serve a niente.
    """
    oggi = now.date()
    giorni = [oggi + timedelta(days=scarto) for scarto in range(FINESTRA_GIORNI)]
    raggruppati = _per_giorno(events, giorni)

    nomi = list(calendars) if calendars is not None else sorted(
        {evento.calendar for evento in events}
    )
    marcatori = calendar_markers(nomi) if len(nomi) > 1 else {}

    cards: list[dict[str, Any]] = [
        _card(_intestazione(oggi), (0, _Y_INTESTAZIONE, USABLE_WIDTH, 32),
              _CORPO_INTESTAZIONE),
        _filetto(_Y_FILETTO_ALTO),
    ]

    if not any(raggruppati.values()):
        cards.append(
            _card(
                f"Nessun evento nei prossimi {FINESTRA_GIORNI} giorni",
                (0, 140, USABLE_WIDTH, 32),
                _CORPO_EVENTO,
                "center",
            )
        )
    else:
        cards.extend(_righe_di_oggi(raggruppati[oggi], marcatori, now, oggi))
        cards.append(_filetto(_Y_FILETTO_BASSO))
        for indice, giorno in enumerate(giorni[1:]):
            cards.append(
                _card(
                    truncate(
                        _riga_giorno(giorno, raggruppati[giorno]),
                        USABLE_WIDTH,
                        _CORPO_GIORNO,
                    ),
                    (0, _Y_PRIMO_GIORNO + indice * _ALTEZZA_RIGA_GIORNO,
                     USABLE_WIDTH, 28),
                    _CORPO_GIORNO,
                )
            )

    if stamp:
        cards.append(
            _card(
                f"agg. {now.strftime('%H:%M')}",
                (360, _Y_AGGIORNAMENTO, 200, 22),
                _CORPO_AGGIORNAMENTO,
                "right",
            )
        )

    return {"page": page_slot, "name": name, "cards": cards}


def _righe_di_oggi(
    eventi: Sequence[Event], marcatori: dict[str, str], now: datetime, oggi: date
) -> list[dict[str, Any]]:
    if not eventi:
        # Oggi non copre nessun evento, ma la finestra non e' vuota (altrimenti
        # saremmo nel ramo "nessun evento nei prossimi giorni"): dirlo evita
        # 230 px di bianco che sembrano un guasto.
        return [
            _card(
                "Nessun evento oggi",
                (0, _Y_PRIMA_RIGA, USABLE_WIDTH, 30),
                _CORPO_EVENTO,
                "center",
            )
        ]

    # Gli eventi gia' conclusi non devono rubare le righe a quelli che devono
    # ancora arrivare. Un evento di tutto il giorno resta valido tutto il
    # giorno anche se la sua "fine" non e' un orario realistico.
    attivi = [e for e in eventi if e.all_day or e.end > now]
    if not attivi:
        return [
            _card(
                "Nessun altro evento oggi",
                (0, _Y_PRIMA_RIGA, USABLE_WIDTH, 30),
                _CORPO_EVENTO,
                "center",
            )
        ]

    visibili = list(attivi[:MAX_EVENTI_OGGI])
    cards: list[dict[str, Any]] = []

    if marcatori:
        x_ora, x_titolo = _LARGHEZZA_MARCATORE + 4, _X_TITOLO_CON_MARCATORI
    else:
        x_ora, x_titolo = 0, 80
    larghezza_titolo = USABLE_WIDTH - x_titolo

    for indice, evento in enumerate(visibili):
        y = _Y_PRIMA_RIGA + indice * _ALTEZZA_RIGA

        if marcatori:
            cards.append(
                _card(
                    # Un calendario non elencato non deve prendere un
                    # marcatore vuoto in silenzio: "?" e' visibile.
                    marcatori.get(evento.calendar, "?"),
                    (0, y, _LARGHEZZA_MARCATORE, 30),
                    _CORPO_MARCATORE,
                )
            )

        ora, titolo = _titolo_riga_oggi(evento, oggi)

        # Un evento di tutto il giorno, o gia' in corso, non ha un'ora da
        # mostrare: niente card vuota nella colonna dell'ora.
        if ora:
            cards.append(
                _card(ora, (x_ora, y, _LARGHEZZA_ORA, 30), _CORPO_EVENTO, "right")
            )
        cards.append(
            _card(
                truncate(titolo, larghezza_titolo, _CORPO_EVENTO),
                (x_titolo, y, larghezza_titolo, 30),
                _CORPO_EVENTO,
            )
        )

    nascosti = len(attivi) - len(visibili)
    if nascosti:
        cards.append(
            _card(
                f"+{nascosti} altri",
                (360, _Y_RIEPILOGO, 200, 24),
                _CORPO_GIORNO,
                "right",
            )
        )

    return cards
