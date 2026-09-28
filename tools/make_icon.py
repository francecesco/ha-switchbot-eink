"""Genera le immagini del brand dell'integrazione.

Home Assistant (dal 2026.8) serve le immagini di un'integrazione custom dalla
sua cartella `brand/`: niente PR al repository `home-assistant/brands`. Il
disegno e' una sagoma generica del pannello, con la barra laterale e qualche
riga d'agenda: niente logo SwitchBot, che e' un marchio.

Uso:
    python -m tools.make_icon
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

DESTINAZIONE = (
    Path(__file__).resolve().parent.parent / "custom_components" / "switchbot_eink" / "brand"
)

# Si disegna in grande e si riduce: il ricampionamento fa da antialiasing.
LATO_DI_LAVORO = 1024
ACCENTO = (59, 130, 246, 255)

TEMI = {
    "chiaro": {
        "cornice": (38, 41, 46, 255),
        "schermo": (244, 244, 240, 255),
        "barra": (120, 124, 130, 255),
        "testo": (38, 41, 46, 255),
        "testo_tenue": (150, 153, 158, 255),
    },
    # Sul tema scuro la cornice quasi nera sparirebbe: si inverte il contrasto.
    "scuro": {
        "cornice": (226, 228, 232, 255),
        "schermo": (52, 56, 62, 255),
        "barra": (150, 154, 160, 255),
        "testo": (236, 237, 240, 255),
        "testo_tenue": (140, 144, 150, 255),
    },
}


def disegna(tema: dict[str, tuple[int, int, int, int]]) -> Image.Image:
    """Il pannello da solo, senza spazio intorno: le specifiche delle immagini
    di Home Assistant vogliono il soggetto ritagliato fino ai bordi."""
    larghezza = LATO_DI_LAVORO
    altezza = int(larghezza * 0.66)
    immagine = Image.new("RGBA", (larghezza, altezza), (0, 0, 0, 0))
    d = ImageDraw.Draw(immagine)
    x0, y0, x1, y1 = 0, 0, larghezza - 1, altezza - 1

    d.rounded_rectangle((x0, y0, x1, y1), radius=70, fill=tema["cornice"])
    bordo = 44
    sx0, sy0, sx1, sy1 = x0 + bordo, y0 + bordo, x1 - bordo, y1 - bordo
    d.rounded_rectangle((sx0, sy0, sx1, sy1), radius=28, fill=tema["schermo"])

    # Barra laterale del firmware: il 30% dello schermo, come sul pannello vero.
    bx1 = sx0 + int((sx1 - sx0) * 0.30)
    d.rounded_rectangle((sx0 + 26, sy0 + 26, bx1 - 20, sy1 - 26), radius=18,
                        fill=tema["barra"])

    # Righe d'agenda: marcatore, ora, titolo.
    cx0 = bx1 + 26
    cx1 = sx1 - 36
    righe = 4
    passo = (sy1 - sy0 - 70) // righe
    lunghezze = (1.0, 0.72, 0.86, 0.55)
    for indice in range(righe):
        cy = sy0 + 48 + indice * passo
        spessore = 34
        d.ellipse((cx0, cy, cx0 + spessore, cy + spessore), fill=ACCENTO)
        ora_x0 = cx0 + spessore + 22
        ora_x1 = ora_x0 + 92
        d.rounded_rectangle((ora_x0, cy, ora_x1, cy + spessore), radius=spessore // 2,
                            fill=tema["testo"])
        titolo_x0 = ora_x1 + 24
        titolo_x1 = titolo_x0 + int((cx1 - titolo_x0) * lunghezze[indice])
        colore = tema["testo"] if indice == 0 else tema["testo_tenue"]
        d.rounded_rectangle((titolo_x0, cy, titolo_x1, cy + spessore),
                            radius=spessore // 2, fill=colore)

    return immagine


def _salva(immagine: Image.Image, nome: str) -> None:
    percorso = DESTINAZIONE / nome
    immagine.save(percorso, optimize=True)
    print(percorso.relative_to(DESTINAZIONE.parent.parent.parent))


def main() -> None:
    DESTINAZIONE.mkdir(parents=True, exist_ok=True)
    for tema, prefisso in (("chiaro", ""), ("scuro", "dark_")):
        pannello = disegna(TEMI[tema])
        for lato, suffisso in ((256, ""), (512, "@2x")):
            # Icona: quadrata per specifica, col pannello a tutta larghezza e
            # centrato in verticale; lo spazio sopra e sotto e' inevitabile.
            ridotto = pannello.resize(
                (lato, round(lato * pannello.height / pannello.width)),
                Image.Resampling.LANCZOS,
            )
            icona = Image.new("RGBA", (lato, lato), (0, 0, 0, 0))
            icona.alpha_composite(ridotto, (0, (lato - ridotto.height) // 2))
            _salva(icona, f"{prefisso}icon{suffisso}.png")

            # Logo: il pannello cosi' com'e', col lato corto a 256 o 512 px.
            logo = pannello.resize(
                (round(lato * pannello.width / pannello.height), lato),
                Image.Resampling.LANCZOS,
            )
            _salva(logo, f"{prefisso}logo{suffisso}.png")


if __name__ == "__main__":
    main()
