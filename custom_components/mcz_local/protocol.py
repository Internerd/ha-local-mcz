"""Frame parsing and command building for the local MCZ Maestro WebSocket.

This module has no Home Assistant dependencies so it can be unit-tested on
its own.

Conventions of the protocol:

* Outgoing frames: ``C|<payload>`` for commands, ``P|PONG`` as keep-alive answer.
* Incoming frames: ``<CODE>|<data>``; ``PING|...`` must be answered.
* All numbers are hexadecimal.
* Temperatures are transmitted as ``°C * 2`` (0.5 °C resolution).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Incoming frame codes ---------------------------------------------------
CODE_PING = "PING"
CODE_PARAMETERS = "00"
CODE_INFO = "01"

# --- Outgoing commands ------------------------------------------------------
CMD_GET_PARAMETERS = "C|RecuperoParametri"
CMD_GET_INFO = "C|RecuperoInfo"
CMD_PONG = "P|PONG"

# --- WriteParametri ids -----------------------------------------------------
PARAM_ALARM_RESET = 1
PARAM_POWER = 34
PARAM_POWER_LEVEL = 36
PARAM_FAN_FRONT = 37
PARAM_FAN_DUCT_1 = 38
PARAM_FAN_DUCT_2 = 39
PARAM_TARGET_TEMPERATURE = 42

VALUE_POWER_ON = 1
VALUE_POWER_OFF = 40
VALUE_ALARM_RESET = 255

POWER_LEVEL_MIN = 1
POWER_LEVEL_MAX = 5

FAN_OFF = 0
FAN_AUTO = 6

# --- RecuperoInfo (code 01) indices ----------------------------------------
INFO_STATE = 0
INFO_FAN_FRONT = 1
INFO_FAN_DUCT_1 = 2
INFO_FAN_DUCT_2 = 3
INFO_EXHAUST_TEMP = 4
INFO_ROOM_TEMP = 5
INFO_BUFFER_TEMP = 6
INFO_WATER_TEMP = 7
INFO_TANK_TEMP = 8
INFO_IGNITER = 9
INFO_ACTIVE_SET = 10
INFO_EXHAUST_FAN_RPM = 11
INFO_AUGER_RPM = 12
INFO_AUGER_RPM_TARGET = 13
INFO_THREE_WAY_VALVE = 14
INFO_PUMP_PWM = 15
INFO_BRAZIER = 16
INFO_ADAPTIVE_MODE = 17
INFO_ACTIVE_VALUE = 20
INFO_CONTROL_MODE = 21
INFO_ECO_STOP = 22
INFO_ROOM_TARGET = 25
INFO_WATER_TARGET = 26
INFO_BOARD_TEMP = 27
INFO_POWER_LEVEL = 28
INFO_FIRMWARE = 29
INFO_HOURS_TO_SERVICE = 42
INFO_ACTIVE_TEMP = 45
INFO_UNIT = 47
INFO_WIFI_PROBE_1 = 51
INFO_WIFI_PROBE_2 = 52
INFO_WIFI_PROBE_3 = 53
INFO_BUFFER_TARGET = 55
INFO_TANK_TARGET = 56
INFO_DHW_TARGET = 57
INFO_RETURN_TEMP = 58

# --- RecuperoParametri (code 00) byte indices ------------------------------
PARAMS_MODEL = 1
PARAMS_FAN_FRONT_PRESENT = 8
PARAMS_FAN_DUCT_1_PRESENT = 14
PARAMS_FAN_DUCT_2_PRESENT = 20
PARAMS_ADAPTIVE_AVAILABLE = 39

MODEL_HYDRO = 1

# Raw temperature values meaning "probe missing / invalid".
TEMPERATURE_SENTINELS = frozenset({0xFB, 0xFC, 0xFE, 0xFF})

# --- Stove states (RecuperoInfo[0]) -----------------------------------------
STATE_OFF = 0
STATE_SHUTDOWN = 40
STATE_COOLING = 41
STATE_AUTO_ECO = 45
STATE_STANDBY = 46
STATE_ALARM_FIRST = 50
STATE_ALARM_LAST = 69
STATE_WAITING_RECIPE_DB = 254
STATE_WAITING_SERIAL = 255

_STATE_KEYS: dict[int, str] = {
    0: "off",
    1: "check",
    2: "cleaning_cold",
    3: "loading_cold",
    4: "start_1_cold",
    5: "start_2_cold",
    6: "cleaning_warm",
    7: "loading_warm",
    8: "start_1_warm",
    9: "start_2_warm",
    10: "stabilization",
    **{code: f"power_{code - 10}" for code in range(11, 31)},
    40: "shutdown",
    41: "cooling",
    42: "cleaning_low",
    43: "cleaning_high",
    44: "auger_unlock",
    45: "auto_eco",
    46: "standby",
    48: "diagnostics",
    49: "auger_loading",
    50: "alarm_a01",
    51: "alarm_a02",
    52: "alarm_a03",
    53: "alarm_a04",
    54: "alarm_a05",
    55: "alarm_a08",
    56: "alarm_a09",
    57: "alarm_a11",
    58: "alarm_a13",
    59: "alarm_a14",
    60: "alarm_a18",
    61: "alarm_a19",
    62: "alarm_a20",
    63: "alarm_a21",
    64: "alarm_a22",
    65: "alarm_a23",
    69: "waiting_safety_alarm",
    254: "waiting_recipe_db",
    255: "waiting_serial",
}
STATE_ALARM_UNKNOWN = "alarm_unknown"
STATE_UNKNOWN = "unknown"
STATE_OPTIONS: list[str] = [
    *dict.fromkeys(_STATE_KEYS.values()),
    STATE_ALARM_UNKNOWN,
    STATE_UNKNOWN,
]

ADAPTIVE_MODE_KEYS = ["manual", "dynamic", "overnight", "comfort", "power"]
CONTROL_MODE_KEYS = ["power", "temperature"]
THREE_WAY_VALVE_KEYS = ["heating", "sanitary"]


class ProtocolError(Exception):
    """Raised when a frame can not be parsed."""


@dataclass
class StoveParameters:
    """Configuration block (``00`` frame)."""

    raw: str
    values: list[int] = field(default_factory=list)

    def get(self, index: int) -> int | None:
        """Return byte ``index`` or None if the frame is too short."""
        if 0 <= index < len(self.values):
            return self.values[index]
        return None

    @property
    def is_hydro(self) -> bool:
        """Return True for water-heating (Hydro) models."""
        return self.get(PARAMS_MODEL) == MODEL_HYDRO

    @property
    def adaptive_available(self) -> bool:
        """Return True if the adaptive (profile) modes are available."""
        return self.get(PARAMS_ADAPTIVE_AVAILABLE) == 1

    def fan_present(self, presence_index: int) -> bool:
        """Return True if the fan behind ``presence_index`` is installed."""
        value = self.get(presence_index)
        return value is not None and value != 0


@dataclass
class StoveInfo:
    """Live telemetry (``01`` frame)."""

    raw: str
    fields: list[str] = field(default_factory=list)

    def raw_field(self, index: int) -> str | None:
        """Return the unparsed hex field at ``index``."""
        if 0 <= index < len(self.fields) and self.fields[index] != "":
            return self.fields[index]
        return None

    def get(self, index: int) -> int | None:
        """Return the integer value of field ``index``."""
        value = self.raw_field(index)
        if value is None:
            return None
        try:
            return int(value, 16)
        except ValueError:
            return None

    def temperature(self, index: int) -> float | None:
        """Return a ``°C * 2`` encoded temperature, None for missing probes."""
        value = self.get(index)
        if value is None or value in TEMPERATURE_SENTINELS:
            return None
        return value / 2

    @property
    def state(self) -> int | None:
        """Return the raw stove state code."""
        return self.get(INFO_STATE)

    @property
    def power_level(self) -> int | None:
        """Return the configured power level (1..5)."""
        value = self.get(INFO_POWER_LEVEL)
        if value is None:
            return None
        return value - 10

    @property
    def firmware(self) -> tuple[int, int, int] | None:
        """Return the board firmware as (major, minor, patch)."""
        value = self.raw_field(INFO_FIRMWARE)
        if value is None or len(value) > 6:
            return None
        value = value.zfill(6)
        try:
            return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
        except ValueError:
            return None


def split_frame(frame: str) -> tuple[str, str]:
    """Split an incoming frame into (code, data)."""
    code, sep, data = frame.partition("|")
    if not sep:
        raise ProtocolError(f"Frame without separator: {frame!r}")
    return code, data


def parse_parameters(data: str) -> StoveParameters:
    """Parse the payload of a ``00`` frame (one hex string, byte-wise)."""
    data = data.strip()
    if len(data) % 2:
        raise ProtocolError(f"Odd-length parameter frame ({len(data)} chars)")
    try:
        values = [int(data[i : i + 2], 16) for i in range(0, len(data), 2)]
    except ValueError as err:
        raise ProtocolError("Parameter frame is not hexadecimal") from err
    return StoveParameters(raw=data, values=values)


def parse_info(data: str) -> StoveInfo:
    """Parse the payload of a ``01`` frame (pipe-separated hex fields)."""
    data = data.strip()
    fields = data.split("|")
    if not fields or fields[0] == "":
        raise ProtocolError("Empty info frame")
    return StoveInfo(raw=data, fields=fields)


def write_parameter(param_id: int, value: int) -> str:
    """Build a ``WriteParametri`` command."""
    return f"C|WriteParametri|{param_id}|{value}"


def encode_temperature(celsius: float) -> int:
    """Encode °C into the ``°C * 2`` wire format."""
    return round(celsius * 2)


def state_key(state: int | None) -> str | None:
    """Return a translation key for a raw stove state."""
    if state is None:
        return None
    if state in _STATE_KEYS:
        return _STATE_KEYS[state]
    if is_alarm(state):
        return STATE_ALARM_UNKNOWN
    return STATE_UNKNOWN


def is_alarm(state: int | None) -> bool:
    """Return True if ``state`` is an alarm state."""
    return state is not None and STATE_ALARM_FIRST <= state <= STATE_ALARM_LAST


def is_off(state: int | None) -> bool:
    """Return True if the stove is switched off (incl. alarm / setup states)."""
    return state in (
        STATE_OFF,
        STATE_WAITING_RECIPE_DB,
        STATE_WAITING_SERIAL,
    ) or is_alarm(state)


def is_heating(state: int | None) -> bool:
    """Return True while the stove is starting up or burning."""
    return (
        state is not None
        and 1 <= state <= 44
        and state
        not in (
            STATE_SHUTDOWN,
            STATE_COOLING,
        )
    )


def adaptive_mode_key(value: int | None) -> str | None:
    """Map RecuperoInfo[17] (0..4 or 10..14) to a profile key."""
    if value is None:
        return None
    index = value - 10 if value >= 10 else value
    if 0 <= index < len(ADAPTIVE_MODE_KEYS):
        return ADAPTIVE_MODE_KEYS[index]
    return None
