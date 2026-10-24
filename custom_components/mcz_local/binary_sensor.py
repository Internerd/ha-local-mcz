"""Binary sensors for the MCZ Maestro (local) integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MczConfigEntry, MczCoordinator, StoveData
from .entity import MczEntity
from .protocol import INFO_BRAZIER, INFO_IGNITER, is_alarm

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MczBinarySensorDescription(BinarySensorEntityDescription):
    """Describes an MCZ binary sensor."""

    value_fn: Callable[[StoveData], bool | None]


def _flag(index: int) -> Callable[[StoveData], bool | None]:
    def value(data: StoveData) -> bool | None:
        raw = data.info.get(index)
        return None if raw is None else raw != 0

    return value


BINARY_SENSORS: tuple[MczBinarySensorDescription, ...] = (
    MczBinarySensorDescription(
        key="alarm",
        translation_key="alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: (
            None if data.info.state is None else is_alarm(data.info.state)
        ),
    ),
    MczBinarySensorDescription(
        key="brazier",
        translation_key="brazier",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_flag(INFO_BRAZIER),
    ),
    MczBinarySensorDescription(
        key="igniter",
        translation_key="igniter",
        device_class=BinarySensorDeviceClass.HEAT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_flag(INFO_IGNITER),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MczConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        MczBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )


class MczBinarySensor(MczEntity, BinarySensorEntity):
    """A flag from the telemetry frame."""

    entity_description: MczBinarySensorDescription

    def __init__(
        self, coordinator: MczCoordinator, description: MczBinarySensorDescription
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the flag."""
        return self.entity_description.value_fn(self.coordinator.data)
