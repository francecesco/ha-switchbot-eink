"""Base comune alle entità del pannello (`sensor.py`, `binary_sensor.py`, `button.py`)."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN
from .coordinator import SwitchBotEinkConfigEntry, SwitchBotEinkCoordinator


class PanelDiagnosticEntity(CoordinatorEntity[SwitchBotEinkCoordinator]):
    """Device info legato al pannello e disponibilità sempre vera.

    `CoordinatorEntity.available` segue `last_update_success`: le entità
    diagnostiche diventerebbero `unavailable` proprio nel momento in cui
    servono (un guasto di pubblicazione), ed è il contrario di quello che
    deve fare un'entità diagnostica, che esiste per dire che qualcosa non
    va. C'è anche un corollario peggiore: il binary sensor
    dell'autenticazione non potrebbe mai accendersi, perché l'unico istante
    in cui dovrebbe farlo è quello in cui il ciclo è appena fallito.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SwitchBotEinkCoordinator,
        entry: SwitchBotEinkConfigEntry,
        unique_id_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        device_id = entry.data[CONF_DEVICE_ID]
        device_name = entry.data.get(CONF_DEVICE_NAME, "SwitchBot E-Ink")
        self._attr_unique_id = f"{device_id}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="SwitchBot",
            model="E-Ink Home Dashboard (W8902500)",
        )

    @property
    def available(self) -> bool:
        return True
