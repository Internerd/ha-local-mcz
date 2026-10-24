"""Tests for frame parsing."""

from __future__ import annotations

import pytest

from custom_components.mcz_local import protocol as p

from .fake_stove import info_frame, params_frame


def test_parse_info() -> None:
    """Fields are hex and temperatures are halved."""
    info = p.parse_info(info_frame())
    assert info.state == 46
    assert info.temperature(p.INFO_ROOM_TEMP) == 18.5
    assert info.temperature(p.INFO_ROOM_TARGET) == 18.0
    assert info.get(p.INFO_EXHAUST_TEMP) == 85
    assert info.power_level == 3
    assert info.firmware == (1, 11, 1)


@pytest.mark.parametrize("raw", [0xFB, 0xFC, 0xFE, 0xFF])
def test_temperature_sentinels(raw: int) -> None:
    """Missing probes are reported as None."""
    info = p.parse_info(info_frame(i6=raw))
    assert info.temperature(p.INFO_BUFFER_TEMP) is None


def test_short_info_frame() -> None:
    """Missing fields return None instead of raising."""
    info = p.parse_info("2e|6")
    assert info.state == 46
    assert info.get(p.INFO_RETURN_TEMP) is None
    assert info.firmware is None


def test_parse_parameters() -> None:
    """The 00 frame is split byte-wise."""
    params = p.parse_parameters(params_frame(hydro=True))
    assert params.is_hydro
    assert params.adaptive_available
    assert params.fan_present(p.PARAMS_FAN_FRONT_PRESENT)
    assert not params.fan_present(p.PARAMS_FAN_DUCT_1_PRESENT)
    assert params.get(1000) is None


def test_parse_parameters_invalid() -> None:
    """Odd length or non-hex data is rejected."""
    with pytest.raises(p.ProtocolError):
        p.parse_parameters("abc")
    with pytest.raises(p.ProtocolError):
        p.parse_parameters("zz")


def test_split_frame() -> None:
    """Code and payload are split at the first pipe."""
    assert p.split_frame("01|2e|6") == ("01", "2e|6")
    with pytest.raises(p.ProtocolError):
        p.split_frame("garbage")


def test_commands() -> None:
    """Write commands use the documented format."""
    assert p.write_parameter(42, p.encode_temperature(21.5)) == "C|WriteParametri|42|43"
    assert (
        p.write_parameter(p.PARAM_POWER, p.VALUE_POWER_OFF) == "C|WriteParametri|34|40"
    )


@pytest.mark.parametrize(
    ("state", "key", "off", "heating", "alarm"),
    [
        (0, "off", True, False, False),
        (1, "check", False, True, False),
        (15, "power_5", False, True, False),
        (30, "power_20", False, True, False),
        (40, "shutdown", False, False, False),
        (46, "standby", False, False, False),
        (50, "alarm_a01", True, False, True),
        (67, "alarm_unknown", True, False, True),
        (255, "waiting_serial", True, False, False),
        (35, "unknown", False, True, False),
    ],
)
def test_states(state: int, key: str, off: bool, heating: bool, alarm: bool) -> None:
    """State helpers classify the documented codes."""
    assert p.state_key(state) == key
    assert key in p.STATE_OPTIONS
    assert p.is_off(state) is off
    assert p.is_heating(state) is heating
    assert p.is_alarm(state) is alarm


def test_adaptive_mode() -> None:
    """Both 0..4 and 10..14 map to the same profiles."""
    assert p.adaptive_mode_key(1) == "dynamic"
    assert p.adaptive_mode_key(11) == "dynamic"
    assert p.adaptive_mode_key(99) is None
