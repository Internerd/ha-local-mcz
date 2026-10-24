"""Base entity for the MCZ Maestro (local) integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import MczCoordinator


def _version(parts: tuple[int, int, int] | None) -> str | None:
    return ".".join(str(part) for part in parts) if parts else None


class MczEntity(CoordinatorEntity[MczCoordinator]):
    """Common device info and unique id handling."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MczCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        data = coordinator.data
        versions = data.versions
        mac = versions.mac if versions else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
            manufacturer=MANUFACTURER,
            model="Maestro Hydro" if data.parameters.is_hydro else "Maestro Air",
            name=entry.title,
            serial_number=versions.serial if versions else None,
            sw_version=_version(data.info.firmware),
            hw_version=versions.panel_type if versions else None,
        )
