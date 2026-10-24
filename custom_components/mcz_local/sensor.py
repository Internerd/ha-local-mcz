"""Sensors for the MCZ Maestro (local) integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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
    ADAPTIVE_MODE_KEYS,
    CONTROL_MODE_KEYS,
    INFO_ACTIVE_TEMP,
    INFO_ACTIVE_VALUE,
    INFO_ADAPTIVE_MODE,
    INFO_AUGER_RPM,
    INFO_AUGER_RPM_TARGET,
    INFO_BOARD_TEMP,
    INFO_BUFFER_TARGET,
    INFO_BUFFER_TEMP,
    INFO_CONTROL_MODE,
    INFO_DHW_TARGET,
    INFO_EXHAUST_FAN_RPM,
    INFO_EXHAUST_TEMP,
    INFO_HOURS_TO_SERVICE,
    INFO_PUMP_PWM,
    INFO_RETURN_TEMP,
    INFO_ROOM_TEMP,
    INFO_TANK_TARGET,
    INFO_TANK_TEMP,
    INFO_THREE_WAY_VALVE,
    INFO_WATER_TARGET,
    INFO_WATER_TEMP,
    INFO_WIFI_PROBE_1,
    INFO_WIFI_PROBE_2,
    INFO_WIFI_PROBE_3,
    STATE_OPTIONS,
    THREE_WAY_VALVE_KEYS,
    StoveParameters,
    adaptive_mode_key,
    state_key,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MczSensorDescription(SensorEntityDescription):
    """Describes an MCZ sensor."""

    value_fn: Callable[[StoveData], float | int | str | None]
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
        key="control_mode",
        translation_key="control_mode",
        device_class=SensorDeviceClass.ENUM,
        options=CONTROL_MODE_KEYS,
        value_fn=_keyed(INFO_CONTROL_MODE, CONTROL_MODE_KEYS),
    ),
    MczSensorDescription(
        key="adaptive_mode",
        translation_key="adaptive_mode",
        device_class=SensorDeviceClass.ENUM,
        options=ADAPTIVE_MODE_KEYS,
        value_fn=lambda data: adaptive_mode_key(data.info.get(INFO_ADAPTIVE_MODE)),
        exists_fn=lambda params: params.adaptive_available,
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
    _temperature_sensor("water_target", INFO_WATER_TARGET, exists_fn=_hydro),
    _temperature_sensor("buffer_target", INFO_BUFFER_TARGET, exists_fn=_hydro),
    _temperature_sensor("tank_target", INFO_TANK_TARGET, exists_fn=_hydro),
    _temperature_sensor("dhw_target", INFO_DHW_TARGET, exists_fn=_hydro),
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
    def native_value(self) -> float | int | str | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
