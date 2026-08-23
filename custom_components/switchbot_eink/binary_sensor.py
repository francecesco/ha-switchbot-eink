"""Entità diagnostica: lo stato dell'autenticazione."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN
from .coordinator import SwitchBotEinkConfigEntry, SwitchBotEinkCoordinator

DESCRIPTION = BinarySensorEntityDescription(
    key="auth",
    translation_key="auth",
    name="Autenticazione",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchBotEinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([AuthBinarySensor(entry.runtime_data, entry)])


class AuthBinarySensor(
    CoordinatorEntity[SwitchBotEinkCoordinator], BinarySensorEntity
):
    """Acceso quando il token non è più valido: è una classe PROBLEM."""

    _attr_has_entity_name = False

    def __init__(
        self, coordinator: SwitchBotEinkCoordinator, entry: SwitchBotEinkConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = DESCRIPTION
        device_id = entry.data[CONF_DEVICE_ID]
        device_name = entry.data.get(CONF_DEVICE_NAME, "SwitchBot E-Ink")
        self._attr_unique_id = f"{device_id}_auth"
        self._attr_name = f"{device_name} autenticazione"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="SwitchBot",
            model="E-Ink Home Dashboard (W8902500)",
        )

    @property
    def is_on(self) -> bool:
        return not self.coordinator.auth_ok
