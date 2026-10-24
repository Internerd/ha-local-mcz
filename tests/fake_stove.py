"""A minimal fake of the stove's WebSocket interface for tests.

The frames are synthetic and only exercise the documented field positions.
"""

from __future__ import annotations

from aiohttp import WSMsgType, web


def info_frame(**overrides: int) -> str:
    """Build a ``01`` payload with 60 fields; values given as ints."""
    fields = [0] * 60
    defaults = {
        0: 46,  # standby
        1: 6,  # front fan auto
        4: 0x55,  # exhaust 85 °C
        5: 37,  # room 18.5 °C
        6: 0xFF,
        7: 0xFF,
        8: 0xFF,
        17: 11,  # dynamic
        21: 1,  # temperature mode
        22: 1,  # eco stop
        36: 7200,  # 2 h total
        44: 42,  # ignitions
        46: 10,  # pellet sensor on
        49: 4,  # sleep: 30 minutes left
        50: 1,  # summer mode
        25: 36,  # target 18 °C
        27: 70,  # board 35 °C
        28: 13,  # power level 3
        42: 1500,
        51: 0xFF,
        52: 0xFF,
        53: 0xFF,
    }
    defaults.update({int(k.removeprefix("i")): v for k, v in overrides.items()})
    for index, value in defaults.items():
        fields[index] = value
    hex_fields = [format(value, "x") for value in fields]
    hex_fields[29] = "010b01"  # firmware 1.11.1
    return "|".join(hex_fields)


def params_frame(hydro: bool = False) -> str:
    """Build a ``00`` payload: 40 bytes."""
    values = [0] * 40
    values[1] = 1 if hydro else 0
    values[2], values[3] = 5, 35  # room setpoint limits in °C
    values[4], values[5] = 30, 80  # water setpoint limits
    values[8] = 1  # front fan present
    values[39] = 1  # adaptive available
    return "".join(format(v, "02x") for v in values)


# Made-up identifiers, same layout as a real 0E answer.
VERSIONS_FRAME = (
    "0000000000000|010b01|5445303620202020|05|MCZ-0000TEST0001|00|1.0.0"
    "|0A1B2C3D4E5F|1.0.0|1.0|N.C.|115200|115200"
)
# Day 0: all T1; day 1: T3 from 08:00 to 17:00; T1/T2/T3 = 9/9/18 °C.
CHRONO_FRAME = "|".join(
    ["5" * 24, "55555555fffffffff5555555", *["0" * 24] * 5, "09", "09", "12"]
)
# Ring buffer: newest entry (A02, 2026-03-13) is not the first slot.
ALARMS_FRAME = "32|69a118c3|33|69b39182|ff|ffffffff|32|699ac8f6"


class FakeStove:
    """aiohttp app answering like the stove."""

    def __init__(self) -> None:
        self.received: list[str] = []
        self.info = info_frame()
        self.params = params_frame()
        self.send_ping = False
        self.versions: str | None = VERSIONS_FRAME
        self.alarms = ALARMS_FRAME
        self.chrono = CHRONO_FRAME
        self.sockets: list[web.WebSocketResponse] = []
        self.app = web.Application()
        self.app.router.add_get("/", self._handler)

    async def _handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.sockets.append(ws)
        if self.send_ping:
            await ws.send_str("PING|1")
        async for msg in ws:
            if msg.type is not WSMsgType.TEXT:
                continue
            self.received.append(msg.data)
            if msg.data == "C|RecuperoParametri":
                await ws.send_str(f"00|{self.params}")
            elif msg.data == "C|RecuperoInfo":
                await ws.send_str(f"01|{self.info}")
            elif msg.data == "C|RecuperoVersioneSW" and self.versions is not None:
                await ws.send_str(f"0E|{self.versions}")
            elif msg.data == "C|RecuperaAllarmi":
                await ws.send_str(f"0A|{self.alarms}")
            elif msg.data == "C|RecuperoGiornoChrono":
                await ws.send_str(f"04|{self.chrono}")
            elif msg.data.startswith("C|ScriviGiornoChrono|"):
                _, _, day, value = msg.data.split("|")
                days = self.chrono.split("|")
                days[int(day)] = value
                self.chrono = "|".join(days)
        return ws

    async def close(self) -> None:
        """Close all open client connections."""
        for ws in self.sockets:
            await ws.close()
