"""Entità diagnostica: quando è avvenuta l'ultima pubblicazione."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SwitchBotEinkConfigEntry, SwitchBotEinkCoordinator
from .entity import PanelDiagnosticEntity

DESCRIPTION = SensorEntityDescription(
    key="last_published",
    translation_key="ultima_pubblicazione",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchBotEinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LastPublishedSensor(entry.runtime_data, entry)])


class LastPublishedSensor(PanelDiagnosticEntity, SensorEntity):
    """Orario dell'ultima pubblicazione riuscita."""

    entity_description = DESCRIPTION

    def __init__(
        self, coordinator: SwitchBotEinkCoordinator, entry: SwitchBotEinkConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "last_published")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_published
