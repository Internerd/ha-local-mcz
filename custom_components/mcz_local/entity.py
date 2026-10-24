"""Base entity for the MCZ Maestro (local) integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import MczCoordinator


class MczEntity(CoordinatorEntity[MczCoordinator]):
    """Common device info and unique id handling."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MczCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        data = coordinator.data
        firmware = data.info.firmware
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            model="Maestro Hydro" if data.parameters.is_hydro else "Maestro Air",
            name=entry.title,
            sw_version=".".join(str(part) for part in firmware) if firmware else None,
        )
