"""Entità diagnostica: lo stato dell'autenticazione."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SwitchBotEinkConfigEntry, SwitchBotEinkCoordinator
from .entity import PanelDiagnosticEntity

DESCRIPTION = BinarySensorEntityDescription(
    key="auth",
    translation_key="autenticazione",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchBotEinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([AuthBinarySensor(entry.runtime_data, entry)])


class AuthBinarySensor(PanelDiagnosticEntity, BinarySensorEntity):
    """Acceso quando il token non è più valido: è una classe PROBLEM."""

    entity_description = DESCRIPTION

    def __init__(
        self, coordinator: SwitchBotEinkCoordinator, entry: SwitchBotEinkConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "auth")

    @property
    def is_on(self) -> bool:
        return not self.coordinator.auth_ok
