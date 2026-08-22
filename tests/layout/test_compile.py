"""Test del compilatore."""
from __future__ import annotations

import json

import pytest

from custom_components.switchbot_eink.layout.compile import (
    EntityValue,
    LayoutError,
    compile_page,
    components_hash,
)
from custom_components.switchbot_eink.layout.schema import validate_page

STATI = {
    "sensor.salotto_temperatura": EntityValue("21.4", "°C"),
    "sensor.lavatrice": EntityValue("in funzione", None),
}


def render_identita(template: str) -> str:
    return template


def risolvi(entity_id: str) -> EntityValue | None:
    return STATI.get(entity_id)


def compila(raw: dict) -> list[dict[str, str]]:
    return compile_page(validate_page(raw), render_identita, risolvi)


def test_una_card_text_produce_un_componente() -> None:
    componenti = compila(
        {"page": "custom1", "cards": [{"type": "text", "text": "ciao", "grid": [0, 0, 4, 1]}]}
    )

    assert len(componenti) == 1
    assert componenti[0]["type"] == "text"
    assert json.loads(componenti[0]["extra"])["content"]["text"] == "ciao"


def test_gli_id_sono_numerici_progressivi_e_unici() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {"type": "text", "text": "a", "grid": [0, 0, 4, 1]},
                {"type": "text", "text": "b", "grid": [0, 1, 4, 1]},
                {"type": "text", "text": "c", "grid": [0, 2, 4, 1]},
            ],
        }
    )

    assert [c["id"] for c in componenti] == ["1", "2", "3"]


def test_una_metric_con_entity_prende_stato_e_unita() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {
                    "type": "metric",
                    "entity": "sensor.salotto_temperatura",
                    "label": "Salotto",
                    "grid": [0, 0, 3, 1],
                }
            ],
        }
    )

    content = json.loads(componenti[0]["extra"])["content"]
    assert content["value"] == "21.4"
    assert content["unit"] == "°C"
    assert content["label"] == "Salotto"


def test_un_value_esplicito_vince_sullo_stato_dell_entita() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {
                    "type": "metric",
                    "entity": "sensor.salotto_temperatura",
                    "value": "99",
                    "label": "L",
                    "grid": [0, 0, 3, 1],
                }
            ],
        }
    )

    assert json.loads(componenti[0]["extra"])["content"]["value"] == "99"


def test_un_unit_esplicito_vince_su_quella_dell_entita() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {
                    "type": "metric",
                    "entity": "sensor.salotto_temperatura",
                    "unit": "gradi",
                    "label": "L",
                    "grid": [0, 0, 3, 1],
                }
            ],
        }
    )

    assert json.loads(componenti[0]["extra"])["content"]["unit"] == "gradi"


def test_entita_sconosciuta_mostra_un_trattino() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {"type": "metric", "entity": "sensor.inesistente", "label": "L",
                 "grid": [0, 0, 3, 1]}
            ],
        }
    )

    assert json.loads(componenti[0]["extra"])["content"]["value"] == "—"


def test_il_widget_predefinito_di_una_metric_e_switchbot_meter() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [{"type": "metric", "value": "1", "label": "L", "grid": [0, 0, 3, 1]}],
        }
    )

    assert componenti[0]["type"] == "switchbotMeter"


def test_i_campi_testuali_passano_dal_renderer() -> None:
    chiamate: list[str] = []

    def render_tracciante(template: str) -> str:
        chiamate.append(template)
        return template.upper()

    componenti = compile_page(
        validate_page(
            {
                "page": "custom1",
                "cards": [{"type": "text", "text": "ciao {{ x }}", "grid": [0, 0, 4, 1]}],
            }
        ),
        render_tracciante,
        risolvi,
    )

    assert chiamate == ["ciao {{ x }}"]
    assert json.loads(componenti[0]["extra"])["content"]["text"] == "CIAO {{ X }}"


def test_position_in_pixel_usata_cosi_com_e() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [{"type": "text", "text": "x", "position": [100, 50, 300, 40]}],
        }
    )

    css = json.loads(componenti[0]["css"])
    assert (css["x"], css["y"], css["w"], css["h"]) == (100, 50, 300, 40)


def test_position_fuori_dall_area_utile_solleva() -> None:
    with pytest.raises(LayoutError, match="esce dall'area utile"):
        compila(
            {
                "page": "custom1",
                "cards": [{"type": "text", "text": "x", "position": [700, 0, 200, 40]}],
            }
        )


def test_card_sovrapposte_sollevano() -> None:
    with pytest.raises(LayoutError, match="si sovrappongono"):
        compila(
            {
                "page": "custom1",
                "cards": [
                    {"type": "text", "text": "a", "position": [0, 0, 200, 100]},
                    {"type": "text", "text": "b", "position": [100, 50, 200, 100]},
                ],
            }
        )


def test_card_adiacenti_non_sollevano() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {"type": "text", "text": "a", "position": [0, 0, 200, 100]},
                {"type": "text", "text": "b", "position": [200, 0, 200, 100]},
            ],
        }
    )

    assert len(componenti) == 2


def test_divider_e_frame_non_hanno_content() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {"type": "divider", "grid": [0, 0, 12, 1]},
                {"type": "frame", "grid": [0, 1, 6, 2]},
            ],
        }
    )

    assert componenti[0]["type"] == "divider"
    assert componenti[1]["type"] == "decorFrame"
    assert json.loads(componenti[0]["extra"])["content"] == {}


def test_image_porta_src_e_alt() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {"type": "image", "src": "https://esempio.test/a.png", "alt": "grafico",
                 "grid": [0, 0, 6, 3]}
            ],
        }
    )

    content = json.loads(componenti[0]["extra"])["content"]
    assert content["src"] == "https://esempio.test/a.png"
    assert content["alt"] == "grafico"


def test_hash_stabile_a_parita_di_componenti() -> None:
    definizione = {
        "page": "custom1",
        "cards": [{"type": "text", "text": "ciao", "grid": [0, 0, 4, 1]}],
    }

    assert components_hash(compila(definizione)) == components_hash(compila(definizione))


def test_hash_diverso_se_il_contenuto_cambia() -> None:
    uno = compila(
        {"page": "custom1", "cards": [{"type": "text", "text": "a", "grid": [0, 0, 4, 1]}]}
    )
    due = compila(
        {"page": "custom1", "cards": [{"type": "text", "text": "b", "grid": [0, 0, 4, 1]}]}
    )

    assert components_hash(uno) != components_hash(due)


def test_sovrapposizione_fra_card_non_adiacenti_viene_rilevata() -> None:
    """Il confronto guarda tutte le card precedenti, non solo l'ultima.

    Qui la prima e la terza si sovrappongono mentre la seconda sta per conto
    suo: un controllo che confrontasse solo con la card precedente lascerebbe
    passare la pagina.
    """
    with pytest.raises(LayoutError, match="0 e 2"):
        compila(
            {
                "page": "custom1",
                "cards": [
                    {"type": "text", "text": "a", "position": [0, 0, 200, 100]},
                    {"type": "text", "text": "b", "position": [400, 0, 200, 100]},
                    {"type": "text", "text": "c", "position": [100, 50, 200, 100]},
                ],
            }
        )
