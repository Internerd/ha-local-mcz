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
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import MczConfigEntry, MczCoordinator, StoveData
from .entity import MczEntity
from .protocol import (
    CHRONO_TEMP_LIMITS,
    INFO_BUFFER_TARGET,
    INFO_DHW_TARGET,
    INFO_SLEEP,
    INFO_TANK_TARGET,
    INFO_WATER_TARGET,
    PARAM_BUFFER_TARGET,
    PARAM_CHRONO_T1,
    PARAM_DHW_TARGET,
    PARAM_POWER_LEVEL,
    PARAM_SLEEP,
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
    SLEEP_MAX_STEPS,
    SLEEP_STEP_MINUTES,
    encode_temperature,
    sleep_minutes,
    sleep_steps,
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
    entities: list[NumberEntity] = [
        MczPowerLevel(coordinator),
        MczSleepTimer(coordinator),
        *(MczChronoTemperature(coordinator, level) for level in range(1, 4)),
    ]
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


class MczSleepTimer(MczEntity, NumberEntity):
    """Switch the stove off after a delay (10-minute steps, 0 = off)."""

    _attr_translation_key = "sleep_timer"
    _attr_native_min_value = 0
    _attr_native_max_value = (SLEEP_MAX_STEPS - 1) * SLEEP_STEP_MINUTES
    _attr_native_step = SLEEP_STEP_MINUTES
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: MczCoordinator) -> None:
        """Initialize the sleep timer."""
        super().__init__(coordinator, "sleep_timer")

    @property
    def native_value(self) -> int | None:
        """Return the remaining time; 0 when the timer is off."""
        return sleep_minutes(self.coordinator.data.info.get(INFO_SLEEP))

    async def async_set_native_value(self, value: float) -> None:
        """Start (or with 0 cancel) the sleep timer."""
        await self.coordinator.async_write((PARAM_SLEEP, sleep_steps(value)))


class MczChronoTemperature(MczEntity, NumberEntity):
    """Chrono program temperature T1, T2 or T3 (whole °C)."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MczCoordinator, level: int) -> None:
        """Initialize T<level>."""
        super().__init__(coordinator, f"chrono_t{level}")
        self._index = level - 1
        self._attr_translation_key = f"chrono_t{level}"
        self._attr_native_min_value, self._attr_native_max_value = CHRONO_TEMP_LIMITS[
            self._index
        ]

    @property
    def available(self) -> bool:
        """Only available once the schedule has been read."""
        return super().available and self.coordinator.data.chrono is not None

    @property
    def native_value(self) -> int | None:
        """Return the program temperature."""
        chrono = self.coordinator.data.chrono
        return chrono.temperatures[self._index] if chrono else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the program temperature, keeping it between its neighbours.

        Only the changed value is checked: stoves can already hold equal
        neighbours (e.g. T1 = T2), which must not block other changes.
        """
        chrono = self.coordinator.data.chrono
        assert chrono is not None
        temperatures = list(chrono.temperatures)
        temperatures[self._index] = int(value)
        below = temperatures[self._index - 1] if self._index > 0 else None
        above = temperatures[self._index + 1] if self._index < 2 else None
        if (below is not None and not below < value) or (
            above is not None and not value < above
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="chrono_order",
                translation_placeholders={
                    "t1": str(temperatures[0]),
                    "t2": str(temperatures[1]),
                    "t3": str(temperatures[2]),
                },
            )
        await self.coordinator.async_write(
            (PARAM_CHRONO_T1 + self._index, int(value)), refresh_chrono=True
        )
