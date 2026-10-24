"""Buttons for the MCZ Maestro (local) integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import MczConfigEntry, MczCoordinator
from .entity import MczEntity
from .protocol import (
    PARAM_ACTIVE_RESET,
    PARAM_ALARM_RESET,
    VALUE_ACTIVE_RESET,
    VALUE_ALARM_RESET,
)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MczConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            MczAlarmResetButton(coordinator),
            MczActiveResetButton(coordinator),
            MczSyncClockButton(coordinator),
        ]
    )


class MczAlarmResetButton(MczEntity, ButtonEntity):
    """Acknowledge / reset an active alarm."""

    _attr_translation_key = "alarm_reset"

    def __init__(self, coordinator: MczCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "alarm_reset")

    async def async_press(self) -> None:
        """Reset the alarm."""
        await self.coordinator.async_write((PARAM_ALARM_RESET, VALUE_ALARM_RESET))


class MczActiveResetButton(MczEntity, ButtonEntity):
    """Reset the Active combustion calibration."""

    _attr_translation_key = "active_reset"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MczCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "active_reset")

    async def async_press(self) -> None:
        """Reset the Active calibration."""
        await self.coordinator.async_write((PARAM_ACTIVE_RESET, VALUE_ACTIVE_RESET))


class MczSyncClockButton(MczEntity, ButtonEntity):
    """Set the stove clock to Home Assistant's local time."""

    _attr_translation_key = "sync_clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MczCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, "sync_clock")

    async def async_press(self) -> None:
        """Write the current local date and time."""
        await self.coordinator.async_set_clock(dt_util.now())
