"""Climate entity for the MCZ Maestro (local) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MczConfigEntry, MczCoordinator
from .entity import MczEntity
from .protocol import (
    INFO_ROOM_TARGET,
    INFO_ROOM_TEMP,
    PARAM_POWER,
    PARAM_TARGET_TEMPERATURE,
    STATE_COOLING,
    STATE_SHUTDOWN,
    VALUE_POWER_OFF,
    VALUE_POWER_ON,
    encode_temperature,
    is_heating,
    is_off,
)

# Half-degree steps for the room setpoint need board firmware >= 1.9.0.
HALF_DEGREE_FIRMWARE = (1, 9, 0)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MczConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the climate entity."""
    async_add_entities([MczClimate(entry.runtime_data)])


class MczClimate(MczEntity, ClimateEntity):
    """Stove on/off and room setpoint."""

    _attr_name = None
    _attr_translation_key = "stove"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: MczCoordinator) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, "climate")

    @property
    def _state(self) -> int | None:
        return self.coordinator.data.info.state

    @property
    def target_temperature_step(self) -> float:
        """Return 0.5 °C on current firmware, 1 °C on older boards."""
        firmware = self.coordinator.data.info.firmware
        if firmware is not None and firmware >= HALF_DEGREE_FIRMWARE:
            return 0.5
        return 1.0

    @property
    def current_temperature(self) -> float | None:
        """Return the room temperature."""
        return self.coordinator.data.info.temperature(INFO_ROOM_TEMP)

    @property
    def target_temperature(self) -> float | None:
        """Return the room setpoint."""
        return self.coordinator.data.info.temperature(INFO_ROOM_TARGET)

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return off while the stove is off or in alarm, heat otherwise."""
        if self._state is None:
            return None
        return HVACMode.OFF if is_off(self._state) else HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return what the stove is currently doing."""
        state = self._state
        if state is None:
            return None
        if is_heating(state):
            return HVACAction.HEATING
        if is_off(state) or state in (STATE_SHUTDOWN, STATE_COOLING):
            return HVACAction.OFF
        return HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch the stove on or off."""
        value = VALUE_POWER_OFF if hvac_mode == HVACMode.OFF else VALUE_POWER_ON
        await self.coordinator.async_write(PARAM_POWER, value)

    async def async_turn_on(self) -> None:
        """Switch the stove on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Switch the stove off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the room setpoint."""
        temperature = kwargs[ATTR_TEMPERATURE]
        await self.coordinator.async_write(
            PARAM_TARGET_TEMPERATURE, encode_temperature(temperature)
        )
