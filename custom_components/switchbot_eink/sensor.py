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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN
from .coordinator import SwitchBotEinkConfigEntry, SwitchBotEinkCoordinator

DESCRIPTION = SensorEntityDescription(
    key="last_published",
    translation_key="last_published",
    name="Ultima pubblicazione",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchBotEinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LastPublishedSensor(entry.runtime_data, entry)])


class LastPublishedSensor(CoordinatorEntity[SwitchBotEinkCoordinator], SensorEntity):
    """Orario dell'ultima pubblicazione riuscita."""

    _attr_has_entity_name = False

    def __init__(
        self, coordinator: SwitchBotEinkCoordinator, entry: SwitchBotEinkConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = DESCRIPTION
        device_id = entry.data[CONF_DEVICE_ID]
        device_name = entry.data.get(CONF_DEVICE_NAME, "SwitchBot E-Ink")
        self._attr_unique_id = f"{device_id}_last_published"
        self._attr_name = f"{device_name} ultima pubblicazione"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="SwitchBot",
            model="E-Ink Home Dashboard (W8902500)",
        )

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_published
