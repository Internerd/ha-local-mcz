"""Integration tests against a fake stove."""

from __future__ import annotations

import asyncio

from freezegun import freeze_time
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
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from .fake_stove import FakeStove, info_frame


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    if hass.config_entries.async_get_entry(entry.entry_id) is None:
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
    device_registry: dr.DeviceRegistry,
) -> None:
    """An air stove gets climate, sensors and only the installed fans."""
    _stove, _ = fake_stove
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    climate = hass.states.get("climate.mcz_maestro")
    assert climate is not None
    assert climate.state == "heat"
    assert climate.attributes["current_temperature"] == 18.5
    assert climate.attributes["temperature"] == 18.0
    assert climate.attributes["target_temp_step"] == 0.5
    assert climate.attributes[ATTR_HVAC_ACTION] == HVACAction.IDLE
    assert climate.attributes["min_temp"] == 5
    assert climate.attributes["max_temp"] == 35

    assert hass.states.get("sensor.mcz_maestro_state").state == "standby"
    assert hass.states.get("select.mcz_maestro_adaptive_mode").state == "dynamic"
    assert hass.states.get("switch.mcz_maestro_eco_stop").state == "on"
    assert hass.states.get("switch.mcz_maestro_auto_mode").state == "on"
    assert hass.states.get("switch.mcz_maestro_summer_mode").state == "on"
    assert hass.states.get("switch.mcz_maestro_pellet_sensor").state == "on"
    assert hass.states.get("switch.mcz_maestro_silent_mode").state == "off"
    assert hass.states.get("sensor.mcz_maestro_operating_hours").state == "2.0"
    assert hass.states.get("sensor.mcz_maestro_ignitions").state == "42"
    assert hass.states.get("sensor.mcz_maestro_last_alarm").state == "alarm_a02"
    assert hass.states.get("sensor.mcz_maestro_last_alarm_time").state == (
        "2026-03-13T04:24:34+00:00"
    )
    assert hass.states.get("number.mcz_maestro_water_setpoint") is None
    assert hass.states.get("number.mcz_maestro_power_level").state == "3"
    assert hass.states.get("select.mcz_maestro_front_fan").state == "auto"
    assert hass.states.get("select.mcz_maestro_ducted_fan_1") is None
    assert hass.states.get("sensor.mcz_maestro_buffer_tank_temperature") is None
    assert hass.states.get("binary_sensor.mcz_maestro_alarm").state == "off"

    device = device_registry.async_get_device(
        identifiers={("mcz_local", config_entry.entry_id)}
    )
    assert device.serial_number == "MCZ-0000TEST0001"
    assert device.sw_version == "1.11.1"
    assert device.hw_version == "TE06"
    assert ("mac", "0a:1b:2c:3d:4e:5f") in device.connections

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
    assert hass.states.get("sensor.mcz_maestro_buffer_tank_temperature").state == "40.0"
    assert hass.states.get("sensor.mcz_maestro_water_temperature").state == "unknown"
    setpoint = hass.states.get("number.mcz_maestro_water_setpoint")
    assert setpoint.attributes["min"] == 30
    assert setpoint.attributes["max"] == 80
    # Buffer limits are 0/0 in the fake frame: no entity.
    assert hass.states.get("number.mcz_maestro_buffer_tank_setpoint") is None


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
        {"entity_id": "climate.mcz_maestro", "temperature": 21.5},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|42|43")

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_TURN_OFF,
        {"entity_id": "climate.mcz_maestro"},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|34|40")

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {"entity_id": "number.mcz_maestro_power_level", "value": 5},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|36|5")

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {"entity_id": "select.mcz_maestro_front_fan", "option": "off"},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|37|0")

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.mcz_maestro_reset_alarm"},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|1|255")

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {"entity_id": "select.mcz_maestro_adaptive_mode", "option": "manual"},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|149|10")
    await _wait_for(stove, "C|WriteParametri|40|0")

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.mcz_maestro_chrono_schedule"},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|1111|1")

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.mcz_maestro_antifreeze"},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|154|0")

    await hass.config.async_set_time_zone("Europe/Berlin")
    with freeze_time("2026-10-24 10:29:00+00:00"):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.mcz_maestro_set_stove_clock"},
            blocking=True,
        )
    await _wait_for(stove, "C|SalvaDataOra|241020261229")


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


async def test_reconnect_after_stove_drops_connection(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
) -> None:
    """When the stove closes the socket the next poll reconnects."""
    stove, _ = fake_stove
    await _setup(hass, config_entry)
    await stove.close()
    coordinator = config_entry.runtime_data
    async with asyncio.timeout(5):
        while coordinator.client.connected:
            await asyncio.sleep(0.01)
    stove.received.clear()
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert stove.received[:2] == ["C|RecuperoParametri", "C|RecuperoInfo"]


async def test_write_error_is_translated(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
) -> None:
    """A failed write surfaces as a translated HomeAssistantError."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    await coordinator.client.close()
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.mcz_maestro_reset_alarm"},
            blocking=True,
        )
    assert err.value.translation_key == "write_failed"


async def test_power_level_out_of_range(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
) -> None:
    """A raw power level outside 11..15 is shown as unknown."""
    stove, _ = fake_stove
    stove.info = info_frame(i28=0)
    await _setup(hass, config_entry)
    assert hass.states.get("number.mcz_maestro_power_level").state == "unknown"


async def test_stove_without_versions(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    short_timeout: None,
) -> None:
    """Setup works when the stove does not answer RecuperoVersioneSW."""
    stove, _ = fake_stove
    stove.versions = None
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    device = device_registry.async_get_device(
        identifiers={("mcz_local", config_entry.entry_id)}
    )
    assert device.serial_number is None


async def test_diagnostics_hide_serial(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
) -> None:
    """Diagnostics contain raw frames but no serial or MAC."""
    from custom_components.mcz_local.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    await _setup(hass, config_entry)
    result = await async_get_config_entry_diagnostics(hass, config_entry)
    text = str(result)
    assert "MCZ-0000TEST0001" not in text
    assert "0A1B2C3D4E5F" not in text
    assert result["info"]["raw"].startswith("2e|")


async def test_brazier_status(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """A motorised brazier reports its motor state; the old binary sensor goes."""
    stove, _ = fake_stove
    stove.info = info_frame(i16=100)
    config_entry.add_to_hass(hass)
    old = entity_registry.async_get_or_create(
        "binary_sensor",
        "mcz_local",
        f"{config_entry.entry_id}_brazier",
        config_entry=config_entry,
    )
    await _setup(hass, config_entry)
    assert hass.states.get("sensor.mcz_maestro_brazier").state == "closing"
    assert entity_registry.async_get(old.entity_id) is None


async def test_brazier_not_present(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
) -> None:
    """255 means no motorised brazier: no entity, no false cleaning warning."""
    stove, _ = fake_stove
    stove.info = info_frame(i16=0xFF)
    await _setup(hass, config_entry)
    assert hass.states.get("sensor.mcz_maestro_brazier") is None


async def test_chrono_sleep_active(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
) -> None:
    """Chrono temps, schedule attributes, sleep timer and Active are wired up."""
    stove, _ = fake_stove
    await _setup(hass, config_entry)

    assert hass.states.get("number.mcz_maestro_chrono_t3").state == "18"
    chrono = hass.states.get("switch.mcz_maestro_chrono_schedule")
    assert chrono.attributes["t1"] == 9
    assert chrono.attributes["monday"][1] == {
        "from": "08:00",
        "to": "17:00",
        "level": 3,
    }
    assert hass.states.get("number.mcz_maestro_sleep_timer").state == "30"
    assert hass.states.get("switch.mcz_maestro_active").state == "off"

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.mcz_maestro_sleep_timer", "value": 60},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|57|7")

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.mcz_maestro_active"}, blocking=True
    )
    await _wait_for(stove, "C|WriteParametri|35|1")

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.mcz_maestro_reset_active_calibration"},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|2|255")

    # T2 = 9 equals T1; raising T3 must still work.
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.mcz_maestro_chrono_t3", "value": 20},
        blocking=True,
    )
    await _wait_for(stove, "C|WriteParametri|1110|20")

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.mcz_maestro_chrono_t2", "value": 25},
            blocking=True,
        )
    assert err.value.translation_key == "chrono_order"


async def test_set_chrono_day_service(
    hass: HomeAssistant,
    fake_stove: tuple[FakeStove, int],
    config_entry: MockConfigEntry,
) -> None:
    """The service writes one day and the schedule is read back."""
    stove, _ = fake_stove
    await _setup(hass, config_entry)

    await hass.services.async_call(
        "mcz_local",
        "set_chrono_day",
        {
            "config_entry_id": config_entry.entry_id,
            "day": "tuesday",
            "periods": [
                {"from": "06:00", "to": "08:30", "level": 3},
                {"from": "22:00", "to": "00:00", "level": 1},
            ],
        },
        blocking=True,
    )
    expected = ["0"] * 48
    expected[12:17] = ["3"] * 5
    expected[44:48] = ["1"] * 4
    frame = "C|ScriviGiornoChrono|2|" + "".join(
        f"{int(''.join(f'{int(s):02b}' for s in expected[i : i + 4]), 2):02x}"
        for i in range(0, 48, 4)
    )
    await _wait_for(stove, frame)
    await hass.async_block_till_done()
    assert hass.states.get("switch.mcz_maestro_chrono_schedule").attributes[
        "tuesday"
    ] == [
        {"from": "06:00", "to": "08:30", "level": 3},
        {"from": "22:00", "to": "24:00", "level": 1},
    ]

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "mcz_local",
            "set_chrono_day",
            {
                "config_entry_id": config_entry.entry_id,
                "day": "tuesday",
                "periods": [{"from": "09:00", "to": "08:00", "level": 1}],
            },
            blocking=True,
        )
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            "mcz_local",
            "set_chrono_day",
            {
                "config_entry_id": config_entry.entry_id,
                "day": "tuesday",
                "periods": [{"from": "09:15", "to": "10:00", "level": 1}],
            },
            blocking=True,
        )
