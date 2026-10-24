"""Integration tests against a fake stove."""

from __future__ import annotations

import asyncio

from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_TEMPERATURE,
    SERVICE_TURN_OFF,
    HVACAction,
)
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN, SERVICE_SET_VALUE
from homeassistant.components.select import (
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .fake_stove import FakeStove, info_frame


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _wait_for(stove: FakeStove, frame: str) -> None:
    async with asyncio.timeout(5):
        while frame not in stove.received:
            await asyncio.sleep(0.01)


async def test_setup_air_stove(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """An air stove gets climate, sensors and only the installed fans."""
    _stove, _ = fake_stove
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    climate = hass.states.get("climate.mcz_maestro_127_0_0_1")
    assert climate is not None
    assert climate.state == "heat"
    assert climate.attributes["current_temperature"] == 18.5
    assert climate.attributes["temperature"] == 18.0
    assert climate.attributes["target_temp_step"] == 0.5
    assert climate.attributes[ATTR_HVAC_ACTION] == HVACAction.IDLE

    assert hass.states.get("sensor.mcz_maestro_127_0_0_1_state").state == "standby"
    assert (
        hass.states.get("sensor.mcz_maestro_127_0_0_1_adaptive_mode").state == "dynamic"
    )
    assert hass.states.get("number.mcz_maestro_127_0_0_1_power_level").state == "3"
    assert hass.states.get("select.mcz_maestro_127_0_0_1_front_fan").state == "auto"
    assert hass.states.get("select.mcz_maestro_127_0_0_1_ducted_fan_1") is None
    assert (
        hass.states.get("sensor.mcz_maestro_127_0_0_1_buffer_tank_temperature") is None
    )
    assert hass.states.get("binary_sensor.mcz_maestro_127_0_0_1_alarm").state == "off"

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_hydro_entities(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
) -> None:
    """Hydro stoves expose water sensors; missing probes are unknown."""
    stove, _ = fake_stove
    from .fake_stove import params_frame

    stove.params = params_frame(hydro=True)
    stove.info = info_frame(i6=0x50, i7=0xFF)
    await _setup(hass, config_entry)
    assert (
        hass.states.get("sensor.mcz_maestro_127_0_0_1_buffer_tank_temperature").state
        == "40.0"
    )
    assert (
        hass.states.get("sensor.mcz_maestro_127_0_0_1_water_temperature").state
        == "unknown"
    )


async def test_commands(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
) -> None:
    """Service calls are translated into WriteParametri frames."""
    stove, _ = fake_stove
    await _setup(hass, config_entry)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {"entity_id": "climate.mcz_maestro_127_0_0_1", "temperature": 21.5},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|42|43")

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_TURN_OFF,
        {"entity_id": "climate.mcz_maestro_127_0_0_1"},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|34|40")

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {"entity_id": "number.mcz_maestro_127_0_0_1_power_level", "value": 5},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|36|5")

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {"entity_id": "select.mcz_maestro_127_0_0_1_front_fan", "option": "off"},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|37|0")

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.mcz_maestro_127_0_0_1_reset_alarm"},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|1|255")


async def test_ping_is_answered(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
) -> None:
    """A PING from the stove is answered with P|PONG."""
    stove, _ = fake_stove
    stove.send_ping = True
    await _setup(hass, config_entry)
    await _wait_for(stove, "P|PONG")


async def test_setup_retry_when_unreachable(
    hass: HomeAssistant, socket_enabled
) -> None:
    """An unreachable stove leads to a setup retry."""
    entry = MockConfigEntry(
        domain="mcz_local", data={"host": "127.0.0.1", "port": 1}, unique_id="x"
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
