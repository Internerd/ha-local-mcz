"""Switches for the MCZ Maestro (local) integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MczConfigEntry, MczCoordinator
from .entity import MczEntity
from .protocol import (
    CHRONO_DAYS,
    INFO_ACTIVE,
    INFO_ANTIFREEZE,
    INFO_CHRONO,
    INFO_CONTROL_MODE,
    INFO_ECO_STOP,
    INFO_PELLET_SENSOR,
    INFO_SILENT_MODE,
    INFO_SOUND,
    INFO_SUMMER_MODE,
    PARAM_ACTIVE,
    PARAM_ANTIFREEZE,
    PARAM_AUTO_MODE,
    PARAM_CHRONO,
    PARAM_ECO_STOP,
    PARAM_PELLET_SENSOR,
    PARAM_SILENT_MODE,
    PARAM_SOUND,
    PARAM_SUMMER_MODE,
    chrono_periods,
)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class MczSwitchDescription(SwitchEntityDescription):
    """A 0/1 setting: written with WriteParametri, read from RecuperoInfo."""

    param_id: int
    info_index: int


SWITCHES: tuple[MczSwitchDescription, ...] = (
    MczSwitchDescription(
        key="auto_mode",
        translation_key="auto_mode",
        param_id=PARAM_AUTO_MODE,
        info_index=INFO_CONTROL_MODE,
    ),
    MczSwitchDescription(
        key="eco_stop",
        translation_key="eco_stop",
        param_id=PARAM_ECO_STOP,
        info_index=INFO_ECO_STOP,
    ),
    MczSwitchDescription(
        key="silent_mode",
        translation_key="silent_mode",
        param_id=PARAM_SILENT_MODE,
        info_index=INFO_SILENT_MODE,
    ),
    MczSwitchDescription(
        key="chrono",
        translation_key="chrono",
        param_id=PARAM_CHRONO,
        info_index=INFO_CHRONO,
    ),
    MczSwitchDescription(
        key="active",
        translation_key="active",
        param_id=PARAM_ACTIVE,
        info_index=INFO_ACTIVE,
    ),
    MczSwitchDescription(
        key="summer_mode",
        translation_key="summer_mode",
        param_id=PARAM_SUMMER_MODE,
        info_index=INFO_SUMMER_MODE,
    ),
    MczSwitchDescription(
        key="antifreeze",
        translation_key="antifreeze",
        param_id=PARAM_ANTIFREEZE,
        info_index=INFO_ANTIFREEZE,
        entity_category=EntityCategory.CONFIG,
    ),
    # Reads 0 = off, 10/11 = on (with / without fuel).
    MczSwitchDescription(
        key="pellet_sensor",
        translation_key="pellet_sensor",
        param_id=PARAM_PELLET_SENSOR,
        info_index=INFO_PELLET_SENSOR,
        entity_category=EntityCategory.CONFIG,
    ),
    MczSwitchDescription(
        key="sound",
        translation_key="sound",
        param_id=PARAM_SOUND,
        info_index=INFO_SOUND,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MczConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        (MczChronoSwitch if description.key == "chrono" else MczSwitch)(
            coordinator, description
        )
        for description in SWITCHES
    )


class MczSwitch(MczEntity, SwitchEntity):
    """A stove setting that can be switched on or off."""

    entity_description: MczSwitchDescription

    def __init__(
        self, coordinator: MczCoordinator, description: MczSwitchDescription
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the setting."""
        value = self.coordinator.data.info.get(self.entity_description.info_index)
        return None if value is None else value != 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Switch the setting on."""
        await self.coordinator.async_write((self.entity_description.param_id, 1))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch the setting off."""
        await self.coordinator.async_write((self.entity_description.param_id, 0))


class MczChronoSwitch(MczSwitch):
    """Chrono on/off; the weekly schedule is exposed as attributes."""

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return T1..T3 and the periods of each day (0..6)."""
        chrono = self.coordinator.data.chrono
        if chrono is None:
            return None
        t1, t2, t3 = chrono.temperatures
        attributes: dict[str, Any] = {"t1": t1, "t2": t2, "t3": t3}
        for day in range(CHRONO_DAYS):
            attributes[f"day_{day}"] = chrono_periods(chrono.days[day])
        return attributes
