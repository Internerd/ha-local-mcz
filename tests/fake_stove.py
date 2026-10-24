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
    values[8] = 1  # front fan present
    values[39] = 1  # adaptive available
    return "".join(format(v, "02x") for v in values)


class FakeStove:
    """aiohttp app answering like the stove."""

    def __init__(self) -> None:
        self.received: list[str] = []
        self.info = info_frame()
        self.params = params_frame()
        self.send_ping = False
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
        return ws

    async def close(self) -> None:
        """Close all open client connections."""
        for ws in self.sockets:
            await ws.close()
