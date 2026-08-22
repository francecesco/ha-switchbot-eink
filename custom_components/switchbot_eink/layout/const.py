"""Geometria del pannello e inventario dei widget.

I valori vengono dal renderer dell'editor web: il pannello `eink-7in3` è
800×480 con una status bar di 64px in alto e 44px in basso.
"""
from __future__ import annotations

from typing import Final

CANVAS_WIDTH: Final = 800
CANVAS_HEIGHT: Final = 480
SAFE_TOP: Final = 64
SAFE_BOTTOM: Final = 44

USABLE_WIDTH: Final = CANVAS_WIDTH
USABLE_HEIGHT: Final = CANVAS_HEIGHT - SAFE_TOP - SAFE_BOTTOM  # 372

GRID_COLS: Final = 12
GRID_ROWS: Final = 6
DEFAULT_GUTTER: Final = 8

# I 19 tipi della famiglia Metric: icona, etichetta, valore, unità.
# I quattro campi sono stringhe libere, quindi sono tile generiche.
METRIC_TYPES: Final[tuple[str, ...]] = (
    "sunTimes",
    "moonPhase",
    "wind",
    "pressure",
    "rainChance",
    "uvIndex",
    "airQuality",
    "visibility",
    "tempRange",
    "aqiValue",
    "pm25",
    "pollen",
    "precipitation",
    "switchbotMeter",
    "switchbotTemperature",
    "feelsLike",
    "switchbotComfort",
    "relativeHumidity",
    "absoluteHumidity",
)

# Tipo usato per le tile generiche quando l'utente non ne sceglie uno.
DEFAULT_METRIC_TYPE: Final = "switchbotMeter"

# Icone note al renderer, utilizzabili in content.icon.
KNOWN_ICONS: Final[tuple[str, ...]] = (
    "sun-times",
    "sun",
    "moon",
    "wind",
    "gauge",
    "rain-chance",
    "uv",
    "air-quality",
    "eye",
    "aqi",
    "temp-range",
    "humidity-drop",
    "thermo-humidity",
)

# Stili ammessi per tipo. Se un tipo non compare qui, passa l'intero style.
STYLE_WHITELIST: Final[dict[str, tuple[str, ...]]] = {
    "text": ("fontSize", "fontWeight", "align", "rotation"),
    "divider": ("rotation",),
    "decorFrame": ("borderWidth", "rotation"),
    "weekday": ("fontSize", "rotation"),
    "dateOnly": ("fontSize", "rotation"),
    "yearOnly": ("fontSize", "rotation"),
    "address": ("fontSize", "rotation"),
    "newsDetail": ("titleFontSize", "bodyFontSize", "rotation"),
    "hackerNewsShowDetail": ("titleFontSize", "bodyFontSize", "rotation"),
    "hackerNewsTopDetail": ("titleFontSize", "bodyFontSize", "rotation"),
}

STYLE_DEFAULTS: Final[dict[str, dict[str, object]]] = {
    "weekday": {"fontSize": 16},
    "dateOnly": {"fontSize": 16},
    "yearOnly": {"fontSize": 16},
    "address": {"fontSize": 16},
}

_METRIC_CONTENT_KEYS: Final[tuple[str, ...]] = ("icon", "label", "value", "unit")

# Chiavi di content ammesse per tipo. relativeHumidity e absoluteHumidity non
# compaiono nella whitelist del client web pur essendo tile Metric: per loro
# passa l'intero content, ed è il comportamento che replichiamo.
CONTENT_WHITELIST: Final[dict[str, tuple[str, ...]]] = {
    **{
        widget_type: _METRIC_CONTENT_KEYS
        for widget_type in METRIC_TYPES
        if widget_type not in ("relativeHumidity", "absoluteHumidity")
    },
    "calendarEventCount": ("title", "unit"),
    "calendarNextEvent": ("title", "text", "unit"),
    "calendarBusyTime": ("title", "text"),
    "calendarWeekStrip": ("unit",),
}

# Colori ammessi dal renderer: il pannello è a 4 livelli di grigio.
COLORS: Final[tuple[str, ...]] = ("black", "white", "gray", "transparent")

MAX_COMPONENT_ID: Final = 2147483647
