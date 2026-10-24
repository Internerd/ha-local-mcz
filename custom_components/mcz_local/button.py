"""Buttons for the MCZ Maestro (local) integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MczConfigEntry, MczCoordinator
from .entity import MczEntity
from .protocol import PARAM_ALARM_RESET, VALUE_ALARM_RESET

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MczConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    async_add_entities([MczAlarmResetButton(entry.runtime_data)])


class MczAlarmResetButton(MczEntity, ButtonEntity):
    """Acknowledge / reset an active alarm."""

    _attr_translation_key = "alarm_reset"

    def __init__(self, coordinator: MczCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "alarm_reset")

    async def async_press(self) -> None:
        """Reset the alarm."""
        await self.coordinator.async_write(PARAM_ALARM_RESET, VALUE_ALARM_RESET)
