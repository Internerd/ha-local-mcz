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
from datetime import UTC, datetime

# --- Incoming frame codes ---------------------------------------------------
CODE_PING = "PING"
CODE_PARAMETERS = "00"
CODE_INFO = "01"
CODE_CHRONO = "04"
CODE_ALARMS = "0A"
CODE_VERSIONS = "0E"

# --- Outgoing commands ------------------------------------------------------
CMD_GET_PARAMETERS = "C|RecuperoParametri"
CMD_GET_INFO = "C|RecuperoInfo"
CMD_GET_ALARMS = "C|RecuperaAllarmi"
CMD_GET_CHRONO = "C|RecuperoGiornoChrono"
CMD_GET_VERSIONS = "C|RecuperoVersioneSW"
CMD_PONG = "P|PONG"

# --- WriteParametri ids -----------------------------------------------------
PARAM_ALARM_RESET = 1
PARAM_ACTIVE_RESET = 2
PARAM_POWER = 34
PARAM_ACTIVE = 35
PARAM_POWER_LEVEL = 36
PARAM_FAN_FRONT = 37
PARAM_FAN_DUCT_1 = 38
PARAM_FAN_DUCT_2 = 39
PARAM_AUTO_MODE = 40
PARAM_ECO_STOP = 41
PARAM_TARGET_TEMPERATURE = 42
PARAM_SILENT_MODE = 45
PARAM_SOUND = 50
PARAM_WATER_TARGET = 51
PARAM_BUFFER_TARGET = 52
PARAM_TANK_TARGET = 53
PARAM_DHW_TARGET = 54
PARAM_SLEEP = 57
PARAM_SUMMER_MODE = 58
PARAM_PELLET_SENSOR = 148
PARAM_ADAPTIVE_MODE = 149
PARAM_ANTIFREEZE = 154
PARAM_CHRONO_T1 = 1108  # 1108..1110 = T1..T3, whole °C
PARAM_CHRONO = 1111

VALUE_POWER_ON = 1
VALUE_POWER_OFF = 40
VALUE_ALARM_RESET = 255
VALUE_ACTIVE_RESET = 255

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
INFO_ACTIVE = 19
INFO_ACTIVE_VALUE = 20
INFO_CONTROL_MODE = 21
INFO_ECO_STOP = 22
INFO_SILENT_MODE = 23
INFO_CHRONO = 24
INFO_ROOM_TARGET = 25
INFO_WATER_TARGET = 26
INFO_BOARD_TEMP = 27
INFO_POWER_LEVEL = 28
INFO_FIRMWARE = 29
INFO_HOURS_TOTAL = 36
INFO_HOURS_POWER_1 = 37  # 37..41 = power level 1..5
INFO_HOURS_TO_SERVICE = 42
INFO_MINUTES_TO_SHUTDOWN = 43
INFO_IGNITIONS = 44
INFO_ACTIVE_TEMP = 45
INFO_PELLET_SENSOR = 46
INFO_UNIT = 47
INFO_SOUND = 48
INFO_SLEEP = 49
INFO_SUMMER_MODE = 50
INFO_WIFI_PROBE_1 = 51
INFO_WIFI_PROBE_2 = 52
INFO_WIFI_PROBE_3 = 53
INFO_BUFFER_TARGET = 55
INFO_TANK_TARGET = 56
INFO_DHW_TARGET = 57
INFO_RETURN_TEMP = 58
INFO_ANTIFREEZE = 59

# --- RecuperoParametri (code 00) byte indices ------------------------------
PARAMS_MODEL = 1
# Setpoint limits, in whole °C (not * 2).
PARAMS_ROOM_MIN = 2
PARAMS_ROOM_MAX = 3
PARAMS_WATER_MIN = 4
PARAMS_WATER_MAX = 5
PARAMS_BUFFER_MIN = 33
PARAMS_BUFFER_MAX = 34
PARAMS_TANK_MIN = 35
PARAMS_TANK_MAX = 36
PARAMS_DHW_MIN = 37
PARAMS_DHW_MAX = 38
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
# Written to WriteParametri|149 on stoves with adaptive mode available.
ADAPTIVE_MODE_OFFSET = 10
THREE_WAY_VALVE_KEYS = ["heating", "sanitary"]

# RecuperoInfo[16]: motorised brazier. 255 = stove has none.
BRAZIER_NOT_PRESENT = 0xFF
BRAZIER_KEYS: dict[int, str] = {0: "ok", 100: "closing", 101: "opening"}


def _firmware(value: str | None) -> tuple[int, int, int] | None:
    """Decode a 3-byte hex version such as ``010b01`` into (1, 11, 1)."""
    if value is None or len(value) > 6:
        return None
    value = value.zfill(6)
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return None


# Sleep timer: WriteParametri|57|n, n = 1..49 steps of 10 minutes, 0 = off.
SLEEP_STEP_MINUTES = 10
SLEEP_MAX_STEPS = 49

# Chrono: 7 days x 48 half-hour slots, 2 bits each (0 = off, 1..3 = T1..T3).
CHRONO_DAYS = 7
# Day index used by the stove; 0 = Sunday (verified on a real stove).
CHRONO_DAY_KEYS = (
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
)
CHRONO_SLOTS = 48
CHRONO_LEVELS = 3
# (min, max) in whole °C for T1, T2, T3; T1 < T2 < T3.
CHRONO_TEMP_LIMITS = ((5, 33), (6, 34), (7, 35))


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

    def limits(self, min_index: int, max_index: int) -> tuple[int, int] | None:
        """Return a (min, max) °C setpoint range, None if not plausible."""
        low, high = self.get(min_index), self.get(max_index)
        if low is None or high is None or not 0 < low < high < 100:
            return None
        return low, high

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

    def hours(self, index: int) -> float | None:
        """Return an operating-time field (seconds) in hours."""
        value = self.get(index)
        if value is None:
            return None
        return round(value / 3600, 1)

    @property
    def state(self) -> int | None:
        """Return the raw stove state code."""
        return self.get(INFO_STATE)

    @property
    def power_level(self) -> int | None:
        """Return the configured power level (1..5)."""
        value = self.get(INFO_POWER_LEVEL)
        if value is None or not POWER_LEVEL_MIN <= value - 10 <= POWER_LEVEL_MAX:
            return None
        return value - 10

    @property
    def firmware(self) -> tuple[int, int, int] | None:
        """Return the board firmware as (major, minor, patch)."""
        return _firmware(self.raw_field(INFO_FIRMWARE))


@dataclass
class StoveVersions:
    """Version block (``0E`` frame)."""

    raw: str
    fields: list[str] = field(default_factory=list)

    def _field(self, index: int) -> str | None:
        if 0 <= index < len(self.fields) and self.fields[index] not in ("", "N.C."):
            return self.fields[index]
        return None

    @property
    def panel_firmware(self) -> tuple[int, int, int] | None:
        """Return the control panel firmware."""
        return _firmware(self._field(1))

    @property
    def panel_type(self) -> str | None:
        """Return the panel type, e.g. ``TE06``."""
        value = self._field(2)
        if value is None:
            return None
        try:
            return bytes.fromhex(value).decode("ascii").strip() or None
        except (ValueError, UnicodeDecodeError):
            return None

    @property
    def serial(self) -> str | None:
        """Return the Wi-Fi module id / serial, e.g. ``MCZ-014A55196D5197``."""
        return self._field(4)

    @property
    def mac(self) -> str | None:
        """Return the module MAC address as ``aa:bb:cc:dd:ee:ff``."""
        value = self._field(7)
        if value is None or len(value) != 12:
            return None
        try:
            int(value, 16)
        except ValueError:
            return None
        return ":".join(value[i : i + 2] for i in range(0, 12, 2)).lower()


@dataclass(frozen=True)
class AlarmEntry:
    """One slot of the alarm history (``0A`` frame)."""

    state: int
    time: datetime


def parse_versions(data: str) -> StoveVersions:
    """Parse the payload of a ``0E`` frame."""
    data = data.strip()
    return StoveVersions(raw=data, fields=data.split("|"))


def parse_alarms(data: str) -> list[AlarmEntry]:
    """Parse ``<state>|<unix time>`` pairs, newest first; empty slots are skipped."""
    fields = data.strip().split("|")
    entries: list[AlarmEntry] = []
    for state, stamp in zip(fields[0::2], fields[1::2], strict=False):
        if stamp.lower() == "ffffffff":
            continue
        try:
            entries.append(
                AlarmEntry(int(state, 16), datetime.fromtimestamp(int(stamp, 16), UTC))
            )
        except (ValueError, OverflowError, OSError):
            continue
    # The stove keeps a ring buffer, so slot order is not chronological.
    return sorted(entries, key=lambda entry: entry.time, reverse=True)


@dataclass(frozen=True)
class ChronoProgram:
    """Weekly schedule (``04`` frame)."""

    days: tuple[tuple[int, ...], ...]
    temperatures: tuple[int, int, int]


def decode_chrono_day(value: str) -> tuple[int, ...]:
    """24 hex chars -> 48 slot levels, MSB first."""
    if len(value) != CHRONO_SLOTS // 2:
        raise ProtocolError(f"Chrono day must be 24 hex chars, got {value!r}")
    try:
        bits = "".join(f"{int(value[i : i + 2], 16):08b}" for i in range(0, 24, 2))
    except ValueError as err:
        raise ProtocolError(f"Chrono day is not hexadecimal: {value!r}") from err
    return tuple(int(bits[i : i + 2], 2) for i in range(0, CHRONO_SLOTS * 2, 2))


def encode_chrono_day(slots: list[int] | tuple[int, ...]) -> str:
    """48 slot levels -> 24 hex chars (inverse of decode_chrono_day)."""
    if len(slots) != CHRONO_SLOTS or any(
        not 0 <= slot <= CHRONO_LEVELS for slot in slots
    ):
        raise ValueError("A chrono day needs 48 slots with levels 0..3")
    bits = "".join(f"{slot:02b}" for slot in slots)
    return "".join(f"{int(bits[i : i + 8], 2):02x}" for i in range(0, 96, 8))


def parse_chrono(data: str) -> ChronoProgram:
    """Parse ``<day0>|...|<day6>|<T1>|<T2>|<T3>``."""
    fields = data.strip().split("|")
    if len(fields) < CHRONO_DAYS + 3:
        raise ProtocolError(f"Chrono frame has {len(fields)} fields")
    days = tuple(decode_chrono_day(day) for day in fields[:CHRONO_DAYS])
    try:
        t1, t2, t3 = (int(value, 16) for value in fields[CHRONO_DAYS : CHRONO_DAYS + 3])
    except ValueError as err:
        raise ProtocolError("Chrono temperatures are not hexadecimal") from err
    return ChronoProgram(days=days, temperatures=(t1, t2, t3))


def write_chrono_day(day: int, slots: list[int] | tuple[int, ...]) -> str:
    """Build the ``ScriviGiornoChrono`` command for day 0..6."""
    if not 0 <= day < CHRONO_DAYS:
        raise ValueError("Chrono day must be 0..6")
    return f"C|ScriviGiornoChrono|{day}|{encode_chrono_day(slots)}"


def chrono_periods(slots: tuple[int, ...]) -> list[dict[str, str | int]]:
    """Group consecutive slots with the same level into from/to periods."""
    periods: list[dict[str, str | int]] = []
    start = 0
    for index in range(1, CHRONO_SLOTS + 1):
        if index == CHRONO_SLOTS or slots[index] != slots[start]:
            if slots[start]:
                periods.append(
                    {
                        "from": _slot_time(start),
                        "to": _slot_time(index),
                        "level": slots[start],
                    }
                )
            start = index
    return periods


def _slot_time(slot: int) -> str:
    return f"{slot // 2:02d}:{30 * (slot % 2):02d}"


def sleep_minutes(raw: int | None) -> int | None:
    """RecuperoInfo[49] -> remaining sleep minutes (0 = off)."""
    if raw is None:
        return None
    return max(raw - 1, 0) * SLEEP_STEP_MINUTES


def sleep_steps(minutes: float) -> int:
    """Minutes -> WriteParametri|57 value (0 = off, else 2..49)."""
    if minutes <= 0:
        return 0
    return min(round(minutes / SLEEP_STEP_MINUTES) + 1, SLEEP_MAX_STEPS)


def set_datetime(value: datetime) -> str:
    """Build the ``SalvaDataOra`` command (``DDMMYYYYHHMM``)."""
    return f"C|SalvaDataOra|{value:%d%m%Y%H%M}"


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


def brazier_key(value: int | None) -> str | None:
    """Map RecuperoInfo[16] to ok / closing / opening."""
    return BRAZIER_KEYS.get(value) if value is not None else None


def adaptive_mode_value(key: str) -> int:
    """Return the WriteParametri|149 value for a profile key."""
    return ADAPTIVE_MODE_KEYS.index(key) + ADAPTIVE_MODE_OFFSET


def adaptive_mode_key(value: int | None) -> str | None:
    """Map RecuperoInfo[17] (0..4 or 10..14) to a profile key."""
    if value is None:
        return None
    index = value - 10 if value >= 10 else value
    if 0 <= index < len(ADAPTIVE_MODE_KEYS):
        return ADAPTIVE_MODE_KEYS[index]
    return None
