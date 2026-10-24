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


def test_ipv6_url() -> None:
    """IPv6 hosts are put in brackets."""
    from custom_components.mcz_local.client import MczClient

    client = MczClient(None, "fe80::1", 81)  # type: ignore[arg-type]
    assert str(client._url) == "ws://[fe80::1]:81/"


def test_parse_versions() -> None:
    """Serial, MAC, panel type and firmware come from the 0E frame."""
    from .fake_stove import VERSIONS_FRAME

    versions = p.parse_versions(VERSIONS_FRAME)
    assert versions.serial == "MCZ-0000TEST0001"
    assert versions.mac == "0a:1b:2c:3d:4e:5f"
    assert versions.panel_type == "TE06"
    assert versions.panel_firmware == (1, 11, 1)
    assert p.parse_versions("x").serial is None


def test_parse_alarms() -> None:
    """Empty slots are skipped and entries sorted newest first."""
    from .fake_stove import ALARMS_FRAME

    alarms = p.parse_alarms(ALARMS_FRAME)
    assert [a.state for a in alarms] == [51, 50, 50]
    assert alarms[0].time.isoformat() == "2026-03-13T04:24:34+00:00"
    assert p.parse_alarms("") == []


def test_set_datetime() -> None:
    """SalvaDataOra uses DDMMYYYYHHMM."""
    from datetime import datetime

    assert p.set_datetime(datetime(2026, 10, 24, 12, 29)) == (
        "C|SalvaDataOra|241020261229"
    )


def test_adaptive_mode_value() -> None:
    """Profiles are written with +10."""
    assert p.adaptive_mode_value("manual") == 10
    assert p.adaptive_mode_value("power") == 14


def test_limits() -> None:
    """Limits are whole °C; implausible ranges are rejected."""
    params = p.parse_parameters(params_frame())
    assert params.limits(p.PARAMS_ROOM_MIN, p.PARAMS_ROOM_MAX) == (5, 35)
    assert params.limits(p.PARAMS_BUFFER_MIN, p.PARAMS_BUFFER_MAX) is None


def test_brazier_key() -> None:
    """Only the documented brazier codes have a meaning."""
    assert p.brazier_key(0) == "ok"
    assert p.brazier_key(101) == "opening"
    assert p.brazier_key(0xFF) is None
    assert p.brazier_key(None) is None


def test_chrono_roundtrip() -> None:
    """Decode and encode are inverse; 2 bits per slot, MSB first."""
    from .fake_stove import CHRONO_FRAME

    chrono = p.parse_chrono(CHRONO_FRAME)
    assert chrono.temperatures == (9, 9, 18)
    assert chrono.days[0] == (1,) * 48
    # 'fd' = 11 11 11 01
    assert p.decode_chrono_day("fd" + "00" * 11)[:5] == (3, 3, 3, 1, 0)
    for day in chrono.days:
        assert p.decode_chrono_day(p.encode_chrono_day(day)) == day
    assert p.encode_chrono_day(chrono.days[1]) == "55555555fffffffff5555555"


def test_chrono_periods() -> None:
    """Consecutive slots are grouped; off slots are left out."""
    from .fake_stove import CHRONO_FRAME

    chrono = p.parse_chrono(CHRONO_FRAME)
    assert p.chrono_periods(chrono.days[0]) == [
        {"from": "00:00", "to": "24:00", "level": 1}
    ]
    assert p.chrono_periods(chrono.days[1]) == [
        {"from": "00:00", "to": "08:00", "level": 1},
        {"from": "08:00", "to": "17:00", "level": 3},
        {"from": "17:00", "to": "24:00", "level": 1},
    ]
    assert p.chrono_periods(chrono.days[2]) == []


def test_chrono_invalid() -> None:
    """Malformed chrono data is rejected."""
    with pytest.raises(p.ProtocolError):
        p.parse_chrono("55|09")
    with pytest.raises(p.ProtocolError):
        p.decode_chrono_day("zz" * 12)
    with pytest.raises(ValueError):
        p.encode_chrono_day([4] * 48)
    with pytest.raises(ValueError):
        p.write_chrono_day(7, [0] * 48)


def test_sleep_conversion() -> None:
    """One step is 10 minutes; the stove shows now + (n - 1) * 10 min."""
    assert p.sleep_minutes(0) == 0
    assert p.sleep_minutes(1) == 0
    assert p.sleep_minutes(4) == 30
    assert p.sleep_minutes(None) is None
    assert p.sleep_steps(0) == 0
    assert p.sleep_steps(30) == 4
    assert p.sleep_steps(480) == 49
    assert p.sleep_steps(9999) == 49
