"""Pulsante che ripubblica subito l'agenda del pannello."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SwitchBotEinkConfigEntry, SwitchBotEinkCoordinator
from .entity import PanelDiagnosticEntity

DESCRIPTION = ButtonEntityDescription(
    key="refresh",
    translation_key="aggiorna_agenda",
    icon="mdi:calendar-refresh",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchBotEinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([RefreshButton(entry.runtime_data, entry)])


class RefreshButton(PanelDiagnosticEntity, ButtonEntity):
    """Come il servizio `refresh`, ma per questo pannello soltanto.

    Evita di passare dagli strumenti per sviluppatori, e si mette in una
    dashboard. Resta disponibile anche a pubblicazione guasta: premerlo e'
    proprio il modo di vedere l'errore.
    """

    entity_description = DESCRIPTION

    def __init__(
        self, coordinator: SwitchBotEinkCoordinator, entry: SwitchBotEinkConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "refresh")

    async def async_press(self) -> None:
        await self.coordinator.async_forza_pubblicazione()
