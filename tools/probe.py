"""Sonda da riga di comando per il SwitchBot E-Ink Home Dashboard.

Serve a rispondere alle domande che non si possono risolvere leggendo il bundle
JavaScript: ogni quanto il pannello si aggiorna, dove cade l'origine delle
coordinate, e se il backend rispetta il content che inviamo.

Uso:
    export SWITCHBOT_USER=mario@example.test
    export SWITCHBOT_PASS=segreta
    export SWITCHBOT_REGION=eu

    python -m tools.probe devices
    python -m tools.probe clock --slot custom1
    python -m tools.probe origin --slot custom1
    python -m tools.probe metric --slot custom1
    python -m tools.probe agenda
    python -m tools.probe homepage [--yes]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, time, timedelta
from typing import Any

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from custom_components.switchbot_eink.api.auth import CanvasAuth  # noqa: E402
from custom_components.switchbot_eink.api.client import SwitchBotCanvasClient  # noqa: E402
from custom_components.switchbot_eink.api.envelope import normalize_region  # noqa: E402
from custom_components.switchbot_eink.api.errors import SwitchBotCanvasError  # noqa: E402
from custom_components.switchbot_eink.api.models import Template, TemplateSummary  # noqa: E402
from custom_components.switchbot_eink.layout.agenda import Event, build_agenda_page  # noqa: E402
from custom_components.switchbot_eink.layout.compile import compile_page  # noqa: E402
from custom_components.switchbot_eink.layout.schema import validate_page  # noqa: E402


def _wire(
    component_id: str,
    widget_type: str,
    name: str,
    css: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, str]:
    """Impacchetta un componente nel wire format: css ed extra sono stringhe JSON."""
    return {
        "id": component_id,
        "type": widget_type,
        "name": name,
        "css": json.dumps(css, separators=(",", ":")),
        "extra": json.dumps(extra, separators=(",", ":")),
    }


def build_clock_component(
    text: str, component_id: str = "1", refresh: str = "1h"
) -> dict[str, str]:
    """Un testo grande in cima all'area utile, per leggere l'orario da lontano.

    `refresh` e' l'ipotesi in prova: e' un campo che scriviamo noi e che il
    backend ripropone al dispositivo. Se e' il pannello a leggerlo per decidere
    ogni quanto tornare a scaricare, la cadenza non si misura, si imposta.
    """
    return _wire(
        component_id,
        "text",
        "Sonda orologio",
        {"x": 240, "y": 0, "w": 560, "h": 80, "z": 1, "fontSize": 56, "align": "center"},
        {
            "dataMode": "text",
            "source": "custom",
            "refresh": refresh,
            "content": {"text": text},
            "locked": False,
            "visible": True,
        },
    )


def build_origin_components() -> list[dict[str, str]]:
    """Due barre agli estremi verticali, per capire dove cade y = 0.

    Se la barra superiore è visibile per intero, l'origine è sotto la status bar.
    Se è tagliata o nascosta, l'origine coincide con il bordo fisico.
    """
    return [
        _wire(
            "1",
            "text",
            "Bordo alto",
            {"x": 0, "y": 0, "w": 800, "h": 24, "z": 1, "fontSize": 20, "align": "center"},
            {
                "dataMode": "text",
                "source": "custom",
                "refresh": "1h",
                "content": {"text": "=== ALTO y=0 ==="},
                "locked": False,
                "visible": True,
            },
        ),
        _wire(
            "2",
            "text",
            "Bordo basso",
            {"x": 0, "y": 348, "w": 800, "h": 24, "z": 1, "fontSize": 20, "align": "center"},
            {
                "dataMode": "text",
                "source": "custom",
                "refresh": "1h",
                "content": {"text": "=== BASSO y=348 ==="},
                "locked": False,
                "visible": True,
            },
        ),
    ]


def build_ruler_components(
    x_valori: list[int], y_valori: list[int]
) -> list[dict[str, str]]:
    """Un righello sulle due assi, per scoprire dove cade davvero l'origine.

    La spec assumeva due fasce orizzontali (safeTop 64, safeBottom 44). Sul
    dispositivo vero c'e' invece una barra verticale a sinistra, quindi l'area
    utile non e' quella che credevamo e va misurata, non dedotta.

    Le etichette sono sfalsate sull'asse opposto a quello che misurano: cosi'
    non si sovrappongono nemmeno con passi fini, e ciascuna comincia esattamente
    alla coordinata che porta scritta (`align: left`, `valign: top`).
    """
    componenti: list[dict[str, str]] = []
    identificativo = 1

    def etichetta(x: int, y: int, testo: str, nome: str) -> None:
        nonlocal identificativo
        componenti.append(
            _wire(
                str(identificativo),
                "text",
                nome,
                {"x": x, "y": y, "w": 76, "h": 30, "z": 1, "fontSize": 18,
                 "align": "left", "valign": "top"},
                {
                    "dataMode": "text",
                    "source": "custom",
                    "refresh": "1h",
                    "content": {"text": testo},
                    "locked": False,
                    "visible": True,
                },
            )
        )
        identificativo += 1

    # Asse x: ogni etichetta a un'altezza diversa, cosi' passi da 10 px non
    # fanno collidere le caselle larghe 76.
    for indice, x in enumerate(x_valori):
        etichetta(x, 30 + indice * 34, f"x{x}", f"x={x}")

    # Asse y: sfalsate in orizzontale, e ben lontane dalla barra laterale.
    for indice, y in enumerate(y_valori):
        etichetta(420 + (indice % 4) * 84, y, f"y{y}", f"y={y}")

    return componenti


def build_frame_components(
    x0: int, y0: int, x1: int, y1: int
) -> list[dict[str, str]]:
    """Quattro etichette agli angoli del rettangolo proposto come area utile.

    Non misura: verifica. Se tutte e quattro si leggono per intero, il
    rettangolo e' interamente visibile e la geometria e' quella giusta.
    """
    larghezza, altezza = 76, 30
    angoli = (
        (x0, y0, "AS"),
        (x1 - larghezza, y0, "AD"),
        (x0, y1 - altezza, "BS"),
        (x1 - larghezza, y1 - altezza, "BD"),
    )

    componenti: list[dict[str, str]] = []
    for indice, (x, y, testo) in enumerate(angoli, start=1):
        componenti.append(
            _wire(
                str(indice),
                "text",
                f"angolo {testo}",
                {"x": x, "y": y, "w": larghezza, "h": altezza, "z": 1,
                 "fontSize": 20, "align": "left", "valign": "top"},
                {
                    "dataMode": "text",
                    "source": "custom",
                    "refresh": "1h",
                    "content": {"text": testo},
                    "locked": False,
                    "visible": True,
                },
            )
        )

    componenti.append(
        _wire(
            "5",
            "text",
            "misure",
            {"x": x0, "y": (y0 + y1) // 2 - 15, "w": x1 - x0, "h": 30, "z": 1,
             "fontSize": 20, "align": "center"},
            {
                "dataMode": "text",
                "source": "custom",
                "refresh": "1h",
                "content": {"text": f"{x0},{y0} - {x1},{y1}"},
                "locked": False,
                "visible": True,
            },
        )
    )
    return componenti


def build_metric_components() -> list[dict[str, str]]:
    """La stessa tile con due dataMode diversi, per vedere quale conserva il content."""
    base_css = {"w": 240, "h": 84, "z": 1}
    return [
        _wire(
            "1",
            "switchbotMeter",
            "Metric dataMode=text",
            {"x": 40, "y": 40, **base_css},
            {
                "dataMode": "text",
                "source": "custom",
                "refresh": "1h",
                "content": {
                    "icon": "thermo-humidity",
                    "label": "MODO TEXT",
                    "value": "42",
                    "unit": "X",
                },
                "locked": False,
                "visible": True,
            },
        ),
        _wire(
            "2",
            "switchbotMeter",
            "Metric dataMode=weather",
            {"x": 400, "y": 40, **base_css},
            {
                "dataMode": "weather",
                "source": "custom",
                "refresh": "1h",
                "content": {
                    "icon": "thermo-humidity",
                    "label": "MODO WEATHER",
                    "value": "99",
                    "unit": "Y",
                },
                "locked": False,
                "visible": True,
            },
        ),
    ]


def sample_agenda_events(now: datetime) -> list[Event]:
    """Eventi finti per vedere l'agenda sul pannello senza Home Assistant.

    Quelli di oggi sono ancorati a scarti dall'istante, mai a orari scritti a
    mano: a tarda sera finiscono su domani, ma la pagina resta valida. Coprono
    i casi che il layout tratta a parte: un evento in corso, uno tutto il
    giorno, due calendari, e piu' eventi di quanti ne stanno oggi, per far
    comparire "+N".
    """
    oggi = datetime.combine(now.date(), time.min)
    domani = oggi + timedelta(days=1)
    dopodomani = oggi + timedelta(days=2)
    ora = now.replace(second=0, microsecond=0)

    def ev(inizio: datetime, durata: timedelta, titolo: str, calendario: str,
           tutto_il_giorno: bool = False) -> Event:
        return Event(inizio, inizio + durata, titolo, tutto_il_giorno, calendario)

    ore = timedelta(hours=1)
    return [
        ev(ora - ore, 2 * ore, "Evento in corso", "Casa"),
        ev(ora + ore, ore, "Riunione settimanale", "Lavoro"),
        ev(ora + 2 * ore, ore, "Pranzo con Marco", "Casa"),
        ev(ora + 3 * ore, ore, "Revisione del progetto e-ink", "Lavoro"),
        ev(ora + 4 * ore, ore, "Spesa", "Casa"),
        ev(ora + 5 * ore, ore, "Chiamata con il fornitore", "Lavoro"),
        ev(ora + 6 * ore, ore, "Palestra", "Casa"),
        ev(ora + 7 * ore, ore, "Cena", "Casa"),
        ev(domani + 8.5 * ore, ore, "Dentista", "Casa"),
        ev(domani + 15 * ore, ore, "Consegna documenti", "Lavoro"),
        ev(dopodomani, timedelta(days=1), "Ferie", "Casa", tutto_il_giorno=True),
    ]


def build_agenda_components(now: datetime) -> list[dict[str, str]]:
    """Lo stesso percorso del coordinator: genera, valida, compila.

    Le card dell'agenda hanno `template: false` e nessuna entita', quindi
    renderer e resolver non vengono mai interpellati sul serio.
    """
    pagina = validate_page(build_agenda_page(sample_agenda_events(now), now))
    return compile_page(pagina, lambda testo: testo, lambda _entita: None)


def read_credentials() -> tuple[str, str, str]:
    """Legge le credenziali dall'ambiente, spiegando cosa manca invece di esplodere."""
    mancanti = [
        nome for nome in ("SWITCHBOT_USER", "SWITCHBOT_PASS") if not os.environ.get(nome)
    ]
    if mancanti:
        raise SystemExit(
            "Variabili d'ambiente mancanti: "
            + ", ".join(mancanti)
            + "\nImpostale prima di eseguire la sonda:\n"
            "  export SWITCHBOT_USER=tua@email\n"
            "  export SWITCHBOT_PASS='la tua password'\n"
            "  export SWITCHBOT_REGION=eu"
        )

    grezza = os.environ.get("SWITCHBOT_REGION", "eu")
    try:
        regione = normalize_region(grezza)
    except ValueError as err:
        raise SystemExit(f"SWITCHBOT_REGION non valida: {err}") from err

    return os.environ["SWITCHBOT_USER"], os.environ["SWITCHBOT_PASS"], regione


async def _connect(session: aiohttp.ClientSession) -> tuple[SwitchBotCanvasClient, str]:
    username, password, region = read_credentials()

    auth = CanvasAuth(session, region)
    tokens = await auth.login(username, password)
    info = await auth.user_info(tokens.access_token, tokens.token_type)
    client = SwitchBotCanvasClient(session, region, tokens, info.user_id)

    devices = await client.list_eink_devices()
    if not devices:
        raise SystemExit("Nessun pannello e-ink trovato sull'account")
    print(f"Pannello: {devices[0].device_name} ({devices[0].device_id})")
    return client, devices[0].device_id


def templates_to_wipe(summaries: list[TemplateSummary]) -> list[TemplateSummary]:
    """Tutto tranne la home.

    La home non si cancella, si sovrascrive: e' la pagina che il pannello mostra
    all'accensione, e cosa faccia il firmware se sparisce non lo sappiamo.
    """
    return [s for s in summaries if s.page_slot != "home"]


async def _wipe(client: SwitchBotCanvasClient, device_id: str, conferma: bool) -> None:
    """Cancella le pagine custom, lasciando solo la home."""
    tutti = await client.list_templates(device_id)
    da_cancellare = templates_to_wipe(tutti)

    if not da_cancellare:
        print("Nessuna pagina custom da cancellare: c'e' gia' solo la home.")
        return

    print("Verranno cancellati definitivamente:")
    for summary in da_cancellare:
        print(f"  id {summary.template_id:<6} slot {summary.page_slot:<11} {summary.name}")

    if not conferma:
        print("\nProva a vuoto: non ho cancellato niente.")
        print("Per cancellare davvero, rilancia con --yes.")
        return

    for summary in da_cancellare:
        await client.delete_template(summary.template_id, device_id)
        print(f"Cancellato {summary.template_id}")

    await client.release(device_id)
    print("Fatto. Sul pannello resta solo la home.")


async def _homepage(
    client: SwitchBotCanvasClient, device_id: str, conferma: bool, forza: bool
) -> None:
    """Mostra da dove il pannello prende la home e, con conferma, la porta sul web.

    Se `pageSource` e' "app" il pannello mostra la home meteo nativa e ignora
    il nostro template home, per quanto sia aggiornato: e' lo stato in cui lo
    lascia un ripristino di fabbrica.

    `forza` rifa' il salvataggio anche con i valori gia' giusti: il pannello
    tiene una copia locale della configurazione, e un ripristino puo' averla
    azzerata mentre il cloud dice ancora "web".
    """
    config = await client.get_home_page_config(device_id)
    print(f"Configurazione attuale della home: {json.dumps(config, ensure_ascii=False)}")

    print("Pagine nel page manager:")
    for pagina in await client.list_pages(device_id):
        print(f"  {json.dumps(pagina, ensure_ascii=False)[:300]}")

    home = [s for s in await client.list_templates(device_id) if s.page_slot == "home"]
    if not home:
        raise SystemExit("Nessun template sullo slot home: pubblicane uno prima (es. `agenda`).")
    template_id = home[0].template_id

    if (
        not forza
        and config.get("pageSource") == "web"
        and config.get("templateID") == template_id
    ):
        print(f"La home e' gia' il template web {template_id}: niente da cambiare.")
        print("Con --force --yes si rifa' comunque il salvataggio.")
        return

    print(f"Da impostare: home web sul template {template_id} ({home[0].name}).")
    if not conferma:
        print("\nProva a vuoto: non ho cambiato niente.")
        print("Per impostarla davvero, rilancia con --yes.")
        return

    await client.set_home_page_web(device_id, template_id)
    await client.release(device_id)
    print(f"Configurazione nuova: {json.dumps(await client.get_home_page_config(device_id))}")
    print("Premi il pulsante 2s per farla scaricare.")


async def _publish(
    client: SwitchBotCanvasClient,
    device_id: str,
    slot: str,
    name: str,
    components: list[dict[str, str]],
) -> None:
    """Riusa il template già presente sullo slot, altrimenti ne crea uno."""
    tutti = await client.list_templates(device_id)
    existing = [t for t in tutti if t.page_slot == slot]

    if tutti:
        print("Template gia' presenti sul pannello:")
        for summary in tutti:
            print(f"  id {summary.template_id:<6} slot {summary.page_slot:<11} {summary.name}")

    if len(existing) > 1:
        print(
            f"Attenzione: sullo slot {slot} ci sono {len(existing)} template. "
            f"Aggiorno il primo (id {existing[0].template_id}); gli altri restano inutilizzati "
            "e potrebbero confondere la misura."
        )

    template = Template(
        template_id=existing[0].template_id if existing else None,
        name=name,
        page_slot=slot,
        device_id=device_id,
        components=components,
    )
    if template.template_id is None:
        template.template_id = await client.create_template(template)
        print(f"Creato template {template.template_id} sullo slot {slot}")
    else:
        print(f"Sovrascrivo il template {template.template_id} sullo slot {slot}")
        await client.update_template(template)

    await client.release(device_id)
    if slot == "home":
        print("Pubblicato sulla home. Premi il pulsante 2s per farla scaricare.")
    else:
        print("Pubblicato. Scorri fino alla pagina custom sul dispositivo.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Sonda per il pannello e-ink SwitchBot")
    parser.add_argument(
        "command",
        choices=[
            "devices",
            "clock",
            "origin",
            "metric",
            "templates",
            "ruler",
            "frame",
            "wipe",
            "preview",
            "agenda",
            "homepage",
        ],
    )
    parser.add_argument(
        "--slot",
        default="home",
        choices=("home", "custom1", "custom2", "custom3", "custom4"),
        help="pagina su cui pubblicare (default: home)",
    )
    parser.add_argument(
        "--refresh",
        default="1h",
        help="valore del campo refresh del componente, es. 5m o 15m (default: 1h)",
    )
    parser.add_argument("--x0", type=int, default=240)
    parser.add_argument("--y0", type=int, default=0)
    parser.add_argument("--x1", type=int, default=800)
    parser.add_argument("--y1", type=int, default=370)
    parser.add_argument("--x-from", type=int, default=0)
    parser.add_argument("--x-to", type=int, default=280)
    parser.add_argument("--x-step", type=int, default=40)
    parser.add_argument("--y-from", type=int, default=0)
    parser.add_argument("--y-to", type=int, default=440)
    parser.add_argument("--y-step", type=int, default=40)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="con `wipe` cancella davvero, con `homepage` imposta la home web; "
        "senza, entrambi fanno una prova a vuoto",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="con `homepage`, salva la configurazione anche se e' gia' quella giusta",
    )
    args = parser.parse_args()

    try:
        async with aiohttp.ClientSession() as session:
            client, device_id = await _connect(session)

            if args.command == "devices":
                for device in await client.list_devices():
                    print(
                        f"  {device.device_id}  {device.device_type:<12} {device.device_name}"
                    )

            elif args.command == "templates":
                for summary in await client.list_templates(device_id):
                    print(f"  {summary.template_id}  {summary.page_slot:<12} {summary.name}")

            elif args.command == "preview":
                # Sola lettura: mostra cosa il backend consegnerebbe al pannello.
                # Serve a distinguere "la nostra scrittura non e' arrivata" da
                # "il dispositivo e' lento a scaricarla".
                sullo_slot = [
                    s
                    for s in await client.list_templates(device_id)
                    if s.page_slot == args.slot
                ]
                if not sullo_slot:
                    raise SystemExit(f"Nessun template sullo slot {args.slot}.")
                dati = await client.preview(sullo_slot[0].template_id, device_id)
                print(json.dumps(dati, indent=2, ensure_ascii=False)[:2000])

            elif args.command == "homepage":
                await _homepage(client, device_id, args.yes, args.force)

            elif args.command == "wipe":
                await _wipe(client, device_id, args.yes)

            elif args.command == "clock":
                now = datetime.now().strftime("%H:%M:%S")
                await _publish(
                    client,
                    device_id,
                    args.slot,
                    "Sonda orologio",
                    [build_clock_component(now, refresh=args.refresh)],
                )
                print(f"Orario pubblicato: {now}")

            elif args.command == "origin":
                await _publish(
                    client, device_id, args.slot, "Sonda origine", build_origin_components()
                )

            elif args.command == "ruler":
                await _publish(
                    client,
                    device_id,
                    args.slot,
                    "Sonda righello",
                    build_ruler_components(
                        list(range(args.x_from, args.x_to + 1, args.x_step)),
                        list(range(args.y_from, args.y_to + 1, args.y_step)),
                    ),
                )

            elif args.command == "frame":
                await _publish(
                    client,
                    device_id,
                    args.slot,
                    "Sonda telaio",
                    build_frame_components(args.x0, args.y0, args.x1, args.y1),
                )

            elif args.command == "agenda":
                await _publish(
                    client,
                    device_id,
                    args.slot,
                    "Agenda",
                    build_agenda_components(datetime.now()),
                )

            elif args.command == "metric":
                await _publish(
                    client, device_id, args.slot, "Sonda metric", build_metric_components()
                )
    except SwitchBotCanvasError as err:
        raise SystemExit(f"Errore nel dialogo con SwitchBot: {err}") from err


if __name__ == "__main__":
    asyncio.run(main())
