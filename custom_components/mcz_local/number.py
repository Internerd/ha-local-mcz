"""Number entities for the MCZ Maestro (local) integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MczConfigEntry, MczCoordinator
from .entity import MczEntity
from .protocol import PARAM_POWER_LEVEL, POWER_LEVEL_MAX, POWER_LEVEL_MIN

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MczConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number entities."""
    async_add_entities([MczPowerLevel(entry.runtime_data)])


class MczPowerLevel(MczEntity, NumberEntity):
    """Power level 1..5."""

    _attr_translation_key = "power_level"
    _attr_native_min_value = POWER_LEVEL_MIN
    _attr_native_max_value = POWER_LEVEL_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: MczCoordinator) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, "power_level")

    @property
    def native_value(self) -> int | None:
        """Return the configured power level."""
        return self.coordinator.data.info.power_level

    async def async_set_native_value(self, value: float) -> None:
        """Set the power level."""
        await self.coordinator.async_write(PARAM_POWER_LEVEL, int(value))
