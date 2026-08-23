"""Test della validazione della definizione YAML."""
from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.switchbot_eink.layout.schema import validate_page


def test_pagina_minima_valida() -> None:
    page = validate_page(
        {"page": "custom1", "cards": [{"type": "text", "text": "ciao", "grid": [0, 0, 4, 1]}]}
    )

    assert page["page"] == "custom1"
    assert page["cards"][0]["type"] == "text"


def test_il_nome_ha_un_default() -> None:
    page = validate_page(
        {"page": "custom1", "cards": [{"type": "text", "text": "x", "grid": [0, 0, 1, 1]}]}
    )

    assert page["name"] == "Home Assistant"


def test_slot_non_valido_rifiutato() -> None:
    with pytest.raises(vol.Invalid):
        validate_page({"page": "custom9", "cards": []})


def test_card_metric_richiede_entity_o_value() -> None:
    with pytest.raises(vol.Invalid, match="entity"):
        validate_page(
            {"page": "custom1", "cards": [{"type": "metric", "grid": [0, 0, 3, 1]}]}
        )


def test_card_metric_con_entity_valida() -> None:
    page = validate_page(
        {
            "page": "custom1",
            "cards": [
                {
                    "type": "metric",
                    "entity": "sensor.salotto_temperatura",
                    "label": "Salotto",
                    "icon": "temp-range",
                    "grid": [0, 0, 3, 1],
                }
            ],
        }
    )

    assert page["cards"][0]["entity"] == "sensor.salotto_temperatura"


def test_card_metric_con_value_esplicito_valida() -> None:
    page = validate_page(
        {
            "page": "custom1",
            "cards": [
                {"type": "metric", "value": "{{ 1 + 1 }}", "label": "L", "grid": [0, 0, 3, 1]}
            ],
        }
    )

    assert page["cards"][0]["value"] == "{{ 1 + 1 }}"


def test_grid_e_position_insieme_rifiutati() -> None:
    with pytest.raises(vol.Invalid, match="grid.*position|position.*grid"):
        validate_page(
            {
                "page": "custom1",
                "cards": [
                    {
                        "type": "text",
                        "text": "x",
                        "grid": [0, 0, 1, 1],
                        "position": [0, 0, 100, 50],
                    }
                ],
            }
        )


def test_card_senza_grid_ne_position_rifiutata() -> None:
    with pytest.raises(vol.Invalid, match="grid|position"):
        validate_page({"page": "custom1", "cards": [{"type": "text", "text": "x"}]})


def test_grid_con_quattro_interi_richiesta() -> None:
    with pytest.raises(vol.Invalid):
        validate_page(
            {"page": "custom1", "cards": [{"type": "text", "text": "x", "grid": [0, 0, 1]}]}
        )


def test_colonna_oltre_la_griglia_rifiutata() -> None:
    with pytest.raises(vol.Invalid):
        validate_page(
            {"page": "custom1", "cards": [{"type": "text", "text": "x", "grid": [12, 0, 1, 1]}]}
        )


def test_tipo_di_card_sconosciuto_rifiutato() -> None:
    with pytest.raises(vol.Invalid):
        validate_page(
            {"page": "custom1", "cards": [{"type": "grafico", "grid": [0, 0, 1, 1]}]}
        )


def test_colore_non_supportato_rifiutato() -> None:
    with pytest.raises(vol.Invalid):
        validate_page(
            {
                "page": "custom1",
                "cards": [
                    {
                        "type": "text",
                        "text": "x",
                        "grid": [0, 0, 1, 1],
                        "style": {"textColor": "rosso"},
                    }
                ],
            }
        )


def test_widget_metric_esplicito_accettato() -> None:
    page = validate_page(
        {
            "page": "custom1",
            "cards": [
                {
                    "type": "metric",
                    "widget": "pressure",
                    "value": "1013",
                    "label": "Pressione",
                    "grid": [0, 0, 3, 1],
                }
            ],
        }
    )

    assert page["cards"][0]["widget"] == "pressure"


def test_grid_con_valore_frazionario_rifiutata() -> None:
    with pytest.raises(vol.Invalid, match="intero"):
        validate_page(
            {"page": "custom1", "cards": [{"type": "text", "text": "x", "grid": [0, 0, 1.5, 1]}]}
        )


def test_grid_con_booleano_rifiutata() -> None:
    with pytest.raises(vol.Invalid, match="intero"):
        validate_page(
            {"page": "custom1", "cards": [{"type": "text", "text": "x", "grid": [0, 0, True, 1]}]}
        )


def test_position_con_valore_frazionario_rifiutata() -> None:
    with pytest.raises(vol.Invalid, match="intero"):
        validate_page(
            {
                "page": "custom1",
                "cards": [{"type": "text", "text": "x", "position": [0, 0, 100.5, 40]}],
            }
        )


def test_il_widget_predefinito_si_applica_solo_alle_metric() -> None:
    page = validate_page(
        {
            "page": "custom1",
            "cards": [
                {"type": "metric", "value": "1", "label": "L", "grid": [0, 0, 3, 1]},
                {"type": "divider", "grid": [0, 1, 12, 1]},
            ],
        }
    )

    assert page["cards"][0]["widget"] == "switchbotMeter"
    assert "widget" not in page["cards"][1], "un divider non ha un widget metric"


def test_una_pagina_senza_card_e_valida() -> None:
    """Una dashboard vuota e' un caso limite legittimo, non un errore."""
    page = validate_page({"page": "custom1", "cards": []})

    assert page["cards"] == []


def test_la_pagina_senza_slot_finisce_sulla_home() -> None:
    """La home e' la pagina che il pannello mostra all'accensione: e' quella che
    vogliamo, e non deve servire dichiararla."""
    page = validate_page({"cards": [{"type": "text", "grid": [0, 0, 2, 1], "text": "x"}]})

    assert page["page"] == "home"


def test_la_home_e_uno_slot_ammesso() -> None:
    page = validate_page(
        {"page": "home", "cards": [{"type": "text", "grid": [0, 0, 2, 1], "text": "x"}]}
    )

    assert page["page"] == "home"


def test_uno_slot_inventato_viene_rifiutato() -> None:
    with pytest.raises(vol.Invalid):
        validate_page(
            {"page": "custom9", "cards": [{"type": "text", "grid": [0, 0, 2, 1], "text": "x"}]}
        )


def test_il_rendering_dei_template_e_attivo_per_default() -> None:
    page = validate_page(
        {"cards": [{"type": "text", "grid": [0, 0, 2, 1], "text": "ciao"}]}
    )

    assert page["cards"][0]["template"] is True


def test_il_rendering_dei_template_si_puo_disattivare() -> None:
    """I titoli degli eventi di calendario sono dati esterni: eseguirli come
    Jinja sarebbe un'iniezione di template."""
    page = validate_page(
        {
            "cards": [
                {"type": "text", "grid": [0, 0, 2, 1], "text": "x", "template": False}
            ]
        }
    )

    assert page["cards"][0]["template"] is False
