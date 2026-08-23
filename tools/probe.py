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
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from custom_components.switchbot_eink.api.auth import CanvasAuth  # noqa: E402
from custom_components.switchbot_eink.api.client import SwitchBotCanvasClient  # noqa: E402
from custom_components.switchbot_eink.api.envelope import normalize_region  # noqa: E402
from custom_components.switchbot_eink.api.errors import SwitchBotCanvasError  # noqa: E402
from custom_components.switchbot_eink.api.models import Template  # noqa: E402


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


def build_clock_component(text: str, component_id: str = "1") -> dict[str, str]:
    """Un testo grande in alto a sinistra, per leggere l'orario da lontano."""
    return _wire(
        component_id,
        "text",
        "Sonda orologio",
        {"x": 0, "y": 0, "w": 800, "h": 80, "z": 1, "fontSize": 56, "align": "center"},
        {
            "dataMode": "text",
            "source": "custom",
            "refresh": "1h",
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
    print("Pubblicato. Scorri fino alla pagina custom sul dispositivo.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Sonda per il pannello e-ink SwitchBot")
    parser.add_argument(
        "command", choices=["devices", "clock", "origin", "metric", "templates"]
    )
    parser.add_argument(
        "--slot",
        default="custom1",
        choices=("custom1", "custom2", "custom3", "custom4"),
        help="pagina custom su cui pubblicare",
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

            elif args.command == "clock":
                now = datetime.now().strftime("%H:%M:%S")
                await _publish(
                    client, device_id, args.slot, "Sonda orologio", [build_clock_component(now)]
                )
                print(f"Orario pubblicato: {now}")

            elif args.command == "origin":
                await _publish(
                    client, device_id, args.slot, "Sonda origine", build_origin_components()
                )

            elif args.command == "metric":
                await _publish(
                    client, device_id, args.slot, "Sonda metric", build_metric_components()
                )
    except SwitchBotCanvasError as err:
        raise SystemExit(f"Errore nel dialogo con SwitchBot: {err}") from err


if __name__ == "__main__":
    asyncio.run(main())
