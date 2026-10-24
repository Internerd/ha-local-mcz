"""Sensors for the MCZ Maestro (local) integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MczConfigEntry, MczCoordinator, StoveData
from .entity import MczEntity
from .protocol import (
    INFO_ACTIVE_TEMP,
    INFO_ACTIVE_VALUE,
    INFO_AUGER_RPM,
    INFO_AUGER_RPM_TARGET,
    INFO_BOARD_TEMP,
    INFO_BUFFER_TEMP,
    INFO_EXHAUST_FAN_RPM,
    INFO_EXHAUST_TEMP,
    INFO_HOURS_POWER_1,
    INFO_HOURS_TO_SERVICE,
    INFO_HOURS_TOTAL,
    INFO_IGNITIONS,
    INFO_MINUTES_TO_SHUTDOWN,
    INFO_PUMP_PWM,
    INFO_RETURN_TEMP,
    INFO_ROOM_TEMP,
    INFO_TANK_TEMP,
    INFO_THREE_WAY_VALVE,
    INFO_WATER_TEMP,
    INFO_WIFI_PROBE_1,
    INFO_WIFI_PROBE_2,
    INFO_WIFI_PROBE_3,
    STATE_OPTIONS,
    THREE_WAY_VALVE_KEYS,
    StoveParameters,
    state_key,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MczSensorDescription(SensorEntityDescription):
    """Describes an MCZ sensor."""

    value_fn: Callable[[StoveData], float | int | str | datetime | None]
    exists_fn: Callable[[StoveParameters], bool] = lambda _: True


def _temperature(index: int) -> Callable[[StoveData], float | None]:
    return lambda data: data.info.temperature(index)


def _raw(index: int) -> Callable[[StoveData], int | None]:
    return lambda data: data.info.get(index)


def _keyed(index: int, keys: list[str]) -> Callable[[StoveData], str | None]:
    def value(data: StoveData) -> str | None:
        raw = data.info.get(index)
        if raw is None or not 0 <= raw < len(keys):
            return None
        return keys[raw]

    return value


def _hours(index: int) -> Callable[[StoveData], float | None]:
    return lambda data: data.info.hours(index)


def _last_alarm_state(data: StoveData) -> str | None:
    return state_key(data.alarms[0].state) if data.alarms else None


def _last_alarm_time(data: StoveData) -> datetime | None:
    return data.alarms[0].time if data.alarms else None


def _hydro(params: StoveParameters) -> bool:
    return params.is_hydro


def _temperature_sensor(key: str, index: int, **kwargs) -> MczSensorDescription:
    return MczSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_temperature(index),
        **kwargs,
    )


SENSORS: tuple[MczSensorDescription, ...] = (
    MczSensorDescription(
        key="state",
        translation_key="state",
        device_class=SensorDeviceClass.ENUM,
        options=STATE_OPTIONS,
        value_fn=lambda data: state_key(data.info.state),
    ),
    _temperature_sensor("room_temperature", INFO_ROOM_TEMP),
    MczSensorDescription(
        key="exhaust_temperature",
        translation_key="exhaust_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_raw(INFO_EXHAUST_TEMP),
    ),
    _temperature_sensor(
        "board_temperature",
        INFO_BOARD_TEMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    MczSensorDescription(
        key="exhaust_fan_speed",
        translation_key="exhaust_fan_speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_raw(INFO_EXHAUST_FAN_RPM),
    ),
    MczSensorDescription(
        key="auger_speed",
        translation_key="auger_speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_raw(INFO_AUGER_RPM),
    ),
    MczSensorDescription(
        key="auger_speed_target",
        translation_key="auger_speed_target",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_raw(INFO_AUGER_RPM_TARGET),
    ),
    MczSensorDescription(
        key="hours_to_service",
        translation_key="hours_to_service",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_raw(INFO_HOURS_TO_SERVICE),
    ),
    MczSensorDescription(
        key="operating_hours",
        translation_key="operating_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_hours(INFO_HOURS_TOTAL),
    ),
    *(
        MczSensorDescription(
            key=f"operating_hours_power_{level}",
            translation_key=f"operating_hours_power_{level}",
            device_class=SensorDeviceClass.DURATION,
            native_unit_of_measurement=UnitOfTime.HOURS,
            state_class=SensorStateClass.TOTAL_INCREASING,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=_hours(INFO_HOURS_POWER_1 + level - 1),
        )
        for level in range(1, 6)
    ),
    MczSensorDescription(
        key="ignitions",
        translation_key="ignitions",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_raw(INFO_IGNITIONS),
    ),
    MczSensorDescription(
        key="minutes_to_shutdown",
        translation_key="minutes_to_shutdown",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=_raw(INFO_MINUTES_TO_SHUTDOWN),
    ),
    MczSensorDescription(
        key="last_alarm",
        translation_key="last_alarm",
        device_class=SensorDeviceClass.ENUM,
        options=STATE_OPTIONS,
        value_fn=_last_alarm_state,
    ),
    MczSensorDescription(
        key="last_alarm_time",
        translation_key="last_alarm_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_alarm_time,
    ),
    MczSensorDescription(
        key="active_value",
        translation_key="active_value",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_raw(INFO_ACTIVE_VALUE),
    ),
    _temperature_sensor(
        "active_temperature",
        INFO_ACTIVE_TEMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    _temperature_sensor(
        "wifi_probe_1", INFO_WIFI_PROBE_1, entity_registry_enabled_default=False
    ),
    _temperature_sensor(
        "wifi_probe_2", INFO_WIFI_PROBE_2, entity_registry_enabled_default=False
    ),
    _temperature_sensor(
        "wifi_probe_3", INFO_WIFI_PROBE_3, entity_registry_enabled_default=False
    ),
    # Hydro (water-heating) models only.
    _temperature_sensor("buffer_temperature", INFO_BUFFER_TEMP, exists_fn=_hydro),
    _temperature_sensor("water_temperature", INFO_WATER_TEMP, exists_fn=_hydro),
    _temperature_sensor("tank_temperature", INFO_TANK_TEMP, exists_fn=_hydro),
    _temperature_sensor("return_temperature", INFO_RETURN_TEMP, exists_fn=_hydro),
    MczSensorDescription(
        key="pump_pwm",
        translation_key="pump_pwm",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_raw(INFO_PUMP_PWM),
        exists_fn=_hydro,
    ),
    MczSensorDescription(
        key="three_way_valve",
        translation_key="three_way_valve",
        device_class=SensorDeviceClass.ENUM,
        options=THREE_WAY_VALVE_KEYS,
        value_fn=_keyed(INFO_THREE_WAY_VALVE, THREE_WAY_VALVE_KEYS),
        exists_fn=_hydro,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MczConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    params = coordinator.data.parameters
    async_add_entities(
        MczSensor(coordinator, description)
        for description in SENSORS
        if description.exists_fn(params)
    )


class MczSensor(MczEntity, SensorEntity):
    """A read-only value from the telemetry frame."""

    entity_description: MczSensorDescription

    def __init__(
        self, coordinator: MczCoordinator, description: MczSensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | str | datetime | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
