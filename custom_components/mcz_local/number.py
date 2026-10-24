"""Number entities for the MCZ Maestro (local) integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MczConfigEntry, MczCoordinator, StoveData
from .entity import MczEntity
from .protocol import (
    INFO_BUFFER_TARGET,
    INFO_DHW_TARGET,
    INFO_TANK_TARGET,
    INFO_WATER_TARGET,
    PARAM_BUFFER_TARGET,
    PARAM_DHW_TARGET,
    PARAM_POWER_LEVEL,
    PARAM_TANK_TARGET,
    PARAM_WATER_TARGET,
    PARAMS_BUFFER_MAX,
    PARAMS_BUFFER_MIN,
    PARAMS_DHW_MAX,
    PARAMS_DHW_MIN,
    PARAMS_TANK_MAX,
    PARAMS_TANK_MIN,
    PARAMS_WATER_MAX,
    PARAMS_WATER_MIN,
    POWER_LEVEL_MAX,
    POWER_LEVEL_MIN,
    encode_temperature,
)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class MczHydroSetpointDescription(NumberEntityDescription):
    """A water setpoint of Hydro models (not verified on a real Hydro stove)."""

    param_id: int
    info_index: int
    limit_indices: tuple[int, int]
    device_class: NumberDeviceClass = NumberDeviceClass.TEMPERATURE
    native_unit_of_measurement: str = UnitOfTemperature.CELSIUS
    native_step: float = 1.0
    mode: NumberMode = NumberMode.BOX


HYDRO_SETPOINTS: tuple[MczHydroSetpointDescription, ...] = (
    MczHydroSetpointDescription(
        key="water_setpoint",
        translation_key="water_setpoint",
        param_id=PARAM_WATER_TARGET,
        info_index=INFO_WATER_TARGET,
        limit_indices=(PARAMS_WATER_MIN, PARAMS_WATER_MAX),
    ),
    MczHydroSetpointDescription(
        key="buffer_setpoint",
        translation_key="buffer_setpoint",
        param_id=PARAM_BUFFER_TARGET,
        info_index=INFO_BUFFER_TARGET,
        limit_indices=(PARAMS_BUFFER_MIN, PARAMS_BUFFER_MAX),
    ),
    MczHydroSetpointDescription(
        key="tank_setpoint",
        translation_key="tank_setpoint",
        param_id=PARAM_TANK_TARGET,
        info_index=INFO_TANK_TARGET,
        limit_indices=(PARAMS_TANK_MIN, PARAMS_TANK_MAX),
    ),
    MczHydroSetpointDescription(
        key="dhw_setpoint",
        translation_key="dhw_setpoint",
        param_id=PARAM_DHW_TARGET,
        info_index=INFO_DHW_TARGET,
        limit_indices=(PARAMS_DHW_MIN, PARAMS_DHW_MAX),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MczConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number entities."""
    coordinator = entry.runtime_data
    params = coordinator.data.parameters
    entities: list[NumberEntity] = [MczPowerLevel(coordinator)]
    if params.is_hydro:
        for description in HYDRO_SETPOINTS:
            if limits := params.limits(*description.limit_indices):
                entities.append(MczHydroSetpoint(coordinator, description, limits))
    async_add_entities(entities)


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
        await self.coordinator.async_write((PARAM_POWER_LEVEL, int(value)))


class MczHydroSetpoint(MczEntity, NumberEntity):
    """Water setpoint with the limits reported by the stove."""

    entity_description: MczHydroSetpointDescription

    def __init__(
        self,
        coordinator: MczCoordinator,
        description: MczHydroSetpointDescription,
        limits: tuple[int, int],
    ) -> None:
        """Initialize the setpoint."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_native_min_value, self._attr_native_max_value = limits
        self._value: Callable[[StoveData], float | None] = lambda data: (
            data.info.temperature(description.info_index)
        )

    @property
    def native_value(self) -> float | None:
        """Return the setpoint."""
        return self._value(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        """Set the setpoint."""
        await self.coordinator.async_write(
            (self.entity_description.param_id, encode_temperature(value))
        )
