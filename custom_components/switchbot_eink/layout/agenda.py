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

# La data di oggi non compare: la barra laterale del firmware la mostra gia'.


@dataclass(frozen=True, slots=True)
class Testi:
    """I testi fissi del pannello in una lingua. I segnaposto sono per `format`."""

    giorni_brevi: tuple[str, ...]
    domani: str
    altri: str
    nessun_evento: str
    nessun_evento_oggi: str
    nessun_altro_evento_oggi: str
    nessun_evento_finestra: str
    nessun_evento_riga: str
    tutto_il_giorno: str
    tutto_il_giorno_sintesi: str
    in_corso: str
    aggiornato: str


TESTI: dict[str, Testi] = {
    "it": Testi(
        giorni_brevi=("LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"),
        domani="DOMANI",
        altri="+{n} altri",
        nessun_evento="Nessun evento",
        nessun_evento_oggi="Nessun evento oggi",
        nessun_altro_evento_oggi="Nessun altro evento oggi",
        nessun_evento_finestra="Nessun evento nei prossimi {n} giorni",
        nessun_evento_riga="nessun evento",
        tutto_il_giorno="Tutto il giorno · {titolo}",
        tutto_il_giorno_sintesi="{titolo} (tutto il giorno)",
        in_corso="In corso · {titolo}",
        aggiornato="agg. {ora}",
    ),
    "en": Testi(
        giorni_brevi=("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"),
        domani="TOMORROW",
        altri="+{n} more",
        nessun_evento="No events",
        nessun_evento_oggi="No events today",
        nessun_altro_evento_oggi="No more events today",
        nessun_evento_finestra="No events in the next {n} days",
        nessun_evento_riga="no events",
        tutto_il_giorno="All day · {titolo}",
        tutto_il_giorno_sintesi="{titolo} (all day)",
        in_corso="Ongoing · {titolo}",
        aggiornato="updated {ora}",
    ),
}

# Chi non ha la sua lingua in tabella legge l'inglese, non l'italiano.
LINGUA_DI_RIPIEGO = "en"


def testi_per(language: str) -> Testi:
    """I testi per un codice di lingua di Home Assistant ("it", "en-GB", ...)."""
    base = language.split("-")[0].split("_")[0].lower()
    return TESTI.get(base, TESTI[LINGUA_DI_RIPIEGO])


FINESTRA_GIORNI = 3
MAX_EVENTI_OGGI = 5
MAX_EVENTI_DOMANI = 2

# Larghezza media di un carattere come frazione del corpo. E' una stima: i font
# del pannello non hanno spaziatura fissa e non ne abbiamo le metriche. Vive in
# un posto solo proprio perche' va tarata con una prova sul dispositivo.
CHAR_WIDTH_RATIO = 0.52

# Geometria, in coordinate dell'area utile (560 x 380).

# Aria fra la barra laterale del firmware e il contenuto: a x=0 i marcatori
# dei calendari finivano attaccati alla barra. Tutto cio' che comincia a
# sinistra parte da qui, e si ferma comunque al bordo destro dell'area.
MARGINE_SINISTRO = 16
_X = MARGINE_SINISTRO
_LARGHEZZA = USABLE_WIDTH - MARGINE_SINISTRO

# Oggi: fino a cinque righe dal bordo alto, poi il riepilogo "+N altri".
_Y_PRIMA_RIGA = 0
_ALTEZZA_RIGA = 34
_Y_RIEPILOGO = 170
_Y_FILETTO = 200
# Domani: un'etichetta (con il suo "+N altri" a destra) e una lista breve.
_Y_DOMANI = 208
_Y_PRIMA_RIGA_DOMANI = 234
_ALTEZZA_RIGA_DOMANI = 30
# Dopodomani, e oltre se la finestra si allarga: una riga riassuntiva ciascuno.
_Y_PRIMO_GIORNO = 298
_ALTEZZA_RIGA_GIORNO = 30
_Y_AGGIORNAMENTO = 352
# La legenda dei marcatori divide l'ultima riga con l'ora di aggiornamento:
# a sinistra fino a poco prima della sua card, che comincia a x=360.
_X_ORA_AGGIORNAMENTO = 360
_LARGHEZZA_LEGENDA = _X_ORA_AGGIORNAMENTO - 8 - MARGINE_SINISTRO

_CORPO_EVENTO = 22
_CORPO_EVENTO_DOMANI = 18
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
    return {"type": "divider", "position": [_X, y, _LARGHEZZA, 2]}


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


def _sintesi(evento: Event, giorno: date, t: Testi) -> str:
    if evento.all_day:
        return t.tutto_il_giorno_sintesi.format(titolo=evento.summary)
    if evento.start.date() < giorno:
        return t.in_corso.format(titolo=evento.summary)
    return f"{evento.start.strftime('%H:%M')} {evento.summary}"


def _riga_giorno(giorno: date, eventi: Sequence[Event], t: Testi) -> str:
    etichetta = f"{t.giorni_brevi[giorno.weekday()]} {giorno.day}"
    if not eventi:
        return f"{etichetta}   {t.nessun_evento_riga}"
    return f"{etichetta}   " + " · ".join(_sintesi(e, giorno, t) for e in eventi)


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


def _titolo_riga(evento: Event, giorno: date, t: Testi) -> tuple[str, str]:
    """(ora, titolo) per la riga di un evento nella lista di un giorno.

    Un evento in corso non ha un'ora d'inizio sensata da mostrare quel giorno:
    viene da un giorno precedente.
    """
    if evento.all_day:
        return "", t.tutto_il_giorno.format(titolo=evento.summary)
    if evento.start.date() < giorno:
        return "", t.in_corso.format(titolo=evento.summary)
    return evento.start.strftime("%H:%M"), evento.summary


def build_agenda_page(
    events: Sequence[Event],
    now: datetime,
    calendars: Sequence[str] | None = None,
    page_slot: str = "home",
    name: str = "Agenda",
    stamp: bool = True,
    language: str = "it",
) -> dict[str, Any]:
    """Costruisce la definizione di pagina dell'agenda.

    `calendars` sono i calendari *scelti dall'utente*, non quelli che oggi hanno
    eventi: i marcatori non devono sparire quando un calendario e' vuoto.

    `stamp=False` omette la card "agg. HH:MM": chi confronta due pagine per
    decidere se ripubblicare deve poter escludere l'orario, altrimenti cambia
    ad ogni minuto e il confronto non serve a niente.

    `language` e' il codice di lingua di Home Assistant: sceglie i testi fissi
    del pannello, con l'inglese per le lingue che non sono in `TESTI`.
    """
    t = testi_per(language)
    oggi = now.date()
    giorni = [oggi + timedelta(days=scarto) for scarto in range(FINESTRA_GIORNI)]
    raggruppati = _per_giorno(events, giorni)

    nomi = list(calendars) if calendars is not None else sorted(
        {evento.calendar for evento in events}
    )
    marcatori = calendar_markers(nomi) if len(nomi) > 1 else {}

    cards: list[dict[str, Any]] = []

    if not any(raggruppati.values()):
        cards.append(
            _card(
                t.nessun_evento_finestra.format(n=FINESTRA_GIORNI),
                (_X, 140, _LARGHEZZA, 32),
                _CORPO_EVENTO,
                "center",
            )
        )
    else:
        cards.extend(_righe_di_oggi(raggruppati[oggi], marcatori, now, oggi, t))
        cards.append(_filetto(_Y_FILETTO))
        cards.extend(_righe_di_domani(raggruppati[giorni[1]], marcatori, giorni[1], t))
        for indice, giorno in enumerate(giorni[2:]):
            cards.append(
                _card(
                    truncate(
                        _riga_giorno(giorno, raggruppati[giorno], t),
                        _LARGHEZZA,
                        _CORPO_GIORNO,
                    ),
                    (_X, _Y_PRIMO_GIORNO + indice * _ALTEZZA_RIGA_GIORNO,
                     _LARGHEZZA, 28),
                    _CORPO_GIORNO,
                )
            )

    if marcatori:
        # Non dipende dall'ora: sta anche nella pagina del confronto, cosi'
        # aggiungere o rinominare un calendario ripubblica.
        cards.append(
            _card(
                truncate(_legenda(marcatori), _LARGHEZZA_LEGENDA, _CORPO_AGGIORNAMENTO),
                (_X, _Y_AGGIORNAMENTO, _LARGHEZZA_LEGENDA, 22),
                _CORPO_AGGIORNAMENTO,
            )
        )

    if stamp:
        cards.append(
            _card(
                t.aggiornato.format(ora=now.strftime("%H:%M")),
                (_X_ORA_AGGIORNAMENTO, _Y_AGGIORNAMENTO, 200, 22),
                _CORPO_AGGIORNAMENTO,
                "right",
            )
        )

    return {"page": page_slot, "name": name, "cards": cards}


def _legenda(marcatori: dict[str, str]) -> str:
    """"L Lavoro · F Famiglia", nell'ordine in cui l'utente ha scelto i calendari."""
    return " · ".join(
        f"{marcatore} {nome.strip()}" for nome, marcatore in marcatori.items()
    )


def _righe_di_oggi(
    eventi: Sequence[Event],
    marcatori: dict[str, str],
    now: datetime,
    oggi: date,
    t: Testi,
) -> list[dict[str, Any]]:
    if not eventi:
        # Oggi non copre nessun evento, ma la finestra non e' vuota (altrimenti
        # saremmo nel ramo "nessun evento nei prossimi giorni"): dirlo evita
        # 230 px di bianco che sembrano un guasto.
        return [
            _card(
                t.nessun_evento_oggi,
                (_X, _Y_PRIMA_RIGA, _LARGHEZZA, 30),
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
                t.nessun_altro_evento_oggi,
                (_X, _Y_PRIMA_RIGA, _LARGHEZZA, 30),
                _CORPO_EVENTO,
                "center",
            )
        ]

    righe, nascosti = _righe_eventi(
        attivi, marcatori, oggi, _Y_PRIMA_RIGA, _ALTEZZA_RIGA, _CORPO_EVENTO,
        MAX_EVENTI_OGGI, t,
    )
    if nascosti:
        righe.append(_altri(nascosti, _Y_RIEPILOGO, t))
    return righe


def _righe_di_domani(
    eventi: Sequence[Event], marcatori: dict[str, str], domani: date, t: Testi
) -> list[dict[str, Any]]:
    """Un'anteprima di domani: etichetta e i primi eventi, in corpo minore.

    Nessun filtro sugli eventi conclusi: domani non e' ancora cominciato, e
    un evento alle 9 viene prima dell'ora di adesso solo come ora del giorno.
    """
    cards = [_card(t.domani, (_X, _Y_DOMANI, 200, 24), _CORPO_GIORNO)]
    if not eventi:
        cards.append(
            _card(
                t.nessun_evento,
                (_X, _Y_PRIMA_RIGA_DOMANI, _LARGHEZZA, 28),
                _CORPO_EVENTO_DOMANI,
            )
        )
        return cards

    righe, nascosti = _righe_eventi(
        eventi, marcatori, domani, _Y_PRIMA_RIGA_DOMANI, _ALTEZZA_RIGA_DOMANI,
        _CORPO_EVENTO_DOMANI, MAX_EVENTI_DOMANI, t,
    )
    cards.extend(righe)
    if nascosti:
        # Sulla riga dell'etichetta: una riga in piu' qui non c'e'.
        cards.append(_altri(nascosti, _Y_DOMANI, t))
    return cards


def _altri(nascosti: int, y: int, t: Testi) -> dict[str, Any]:
    """Far sparire eventi in silenzio e' peggio che dire quanti ne mancano."""
    return _card(t.altri.format(n=nascosti), (360, y, 200, 24), _CORPO_GIORNO, "right")


def _righe_eventi(
    eventi: Sequence[Event],
    marcatori: dict[str, str],
    giorno: date,
    y_iniziale: int,
    altezza_riga: int,
    corpo: int,
    massimo: int,
    t: Testi,
) -> tuple[list[dict[str, Any]], int]:
    """Le righe marcatore/ora/titolo dei primi `massimo` eventi, e quanti ne
    restano fuori."""
    visibili = list(eventi[:massimo])
    cards: list[dict[str, Any]] = []

    if marcatori:
        x_ora, x_titolo = _X + _LARGHEZZA_MARCATORE + 4, _X + _X_TITOLO_CON_MARCATORI
    else:
        x_ora, x_titolo = _X, _X + 80
    larghezza_titolo = USABLE_WIDTH - x_titolo
    altezza = altezza_riga - 4

    for indice, evento in enumerate(visibili):
        y = y_iniziale + indice * altezza_riga

        if marcatori:
            cards.append(
                _card(
                    # Un calendario non elencato non deve prendere un
                    # marcatore vuoto in silenzio: "?" e' visibile.
                    marcatori.get(evento.calendar, "?"),
                    (_X, y, _LARGHEZZA_MARCATORE, altezza),
                    _CORPO_MARCATORE,
                )
            )

        ora, titolo = _titolo_riga(evento, giorno, t)

        # Un evento di tutto il giorno, o gia' in corso, non ha un'ora da
        # mostrare: niente card vuota nella colonna dell'ora.
        if ora:
            cards.append(
                _card(ora, (x_ora, y, _LARGHEZZA_ORA, altezza), corpo, "right")
            )
        cards.append(
            _card(
                truncate(titolo, larghezza_titolo, corpo),
                (x_titolo, y, larghezza_titolo, altezza),
                corpo,
            )
        )

    return cards, len(eventi) - len(visibili)
