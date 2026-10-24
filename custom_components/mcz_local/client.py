"""Async WebSocket client for the local MCZ Maestro interface."""

from __future__ import annotations

import asyncio
from collections import deque
import contextlib
from datetime import datetime
import logging

import aiohttp
from yarl import URL

from .protocol import (
    CMD_GET_ALARMS,
    CMD_GET_CHRONO,
    CMD_GET_INFO,
    CMD_GET_PARAMETERS,
    CMD_GET_VERSIONS,
    CMD_PONG,
    CODE_ALARMS,
    CODE_CHRONO,
    CODE_INFO,
    CODE_PARAMETERS,
    CODE_PING,
    CODE_VERSIONS,
    AlarmEntry,
    ChronoProgram,
    ProtocolError,
    StoveInfo,
    StoveParameters,
    StoveVersions,
    parse_alarms,
    parse_chrono,
    parse_info,
    parse_parameters,
    parse_versions,
    set_datetime,
    split_frame,
    write_chrono_day,
    write_parameter,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 10
RESPONSE_TIMEOUT = 10
RAW_FRAME_HISTORY = 20


class MczConnectionError(Exception):
    """Raised when the stove can not be reached or stops answering."""


class MczTimeoutError(MczConnectionError):
    """Raised when the stove did not answer a request in time."""


class MczClient:
    """Keeps one WebSocket open to the stove and correlates replies by code."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int) -> None:
        """Initialize the client."""
        self._session = session
        self._url = URL.build(scheme="ws", host=host, port=port, path="/")
        self._closed = False
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._reader: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._waiters: dict[str, list[asyncio.Future[str]]] = {}
        self.parameters: StoveParameters | None = None
        self.info: StoveInfo | None = None
        self.versions: StoveVersions | None = None
        self.alarms: list[AlarmEntry] | None = None
        self.chrono: ChronoProgram | None = None
        self.recent_frames: deque[str] = deque(maxlen=RAW_FRAME_HISTORY)

    @property
    def connected(self) -> bool:
        """Return True while the WebSocket is open."""
        return self._ws is not None and not self._ws.closed

    async def connect(self) -> None:
        """Open the WebSocket and load the stove configuration."""
        if self._closed:
            raise MczConnectionError("Client is closed")
        if self.connected:
            return
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                self._ws = await self._session.ws_connect(self._url, autoping=True)
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise MczConnectionError(f"Cannot connect to {self._url}: {err}") from err
        self._reader = asyncio.create_task(self._read_loop(self._ws))
        await self.fetch_parameters()
        if self.versions is None:
            # Optional: older firmware may not answer; the next connect retries.
            with contextlib.suppress(MczTimeoutError):
                await self.fetch_versions()

    async def disconnect(self) -> None:
        """Close the WebSocket."""
        ws, self._ws = self._ws, None
        reader, self._reader = self._reader, None
        if ws is not None:
            await ws.close()
        if reader is not None:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader
        self._fail_waiters(MczConnectionError("Disconnected"))

    async def close(self) -> None:
        """Disconnect for good; later connect() calls fail."""
        self._closed = True
        await self.disconnect()

    async def fetch_parameters(self) -> StoveParameters:
        """Request the configuration block (``00``)."""
        data = await self._request(CMD_GET_PARAMETERS, CODE_PARAMETERS)
        try:
            self.parameters = parse_parameters(data)
        except ProtocolError as err:
            raise MczConnectionError(str(err)) from err
        return self.parameters

    async def fetch_info(self) -> StoveInfo:
        """Request live telemetry (``01``)."""
        data = await self._request(CMD_GET_INFO, CODE_INFO)
        try:
            self.info = parse_info(data)
        except ProtocolError as err:
            raise MczConnectionError(str(err)) from err
        return self.info

    async def fetch_versions(self) -> StoveVersions:
        """Request firmware versions and serial (``0E``)."""
        data = await self._request(CMD_GET_VERSIONS, CODE_VERSIONS)
        self.versions = parse_versions(data)
        return self.versions

    async def fetch_alarms(self) -> list[AlarmEntry]:
        """Request the alarm history (``0A``), newest first."""
        data = await self._request(CMD_GET_ALARMS, CODE_ALARMS)
        self.alarms = parse_alarms(data)
        return self.alarms

    async def fetch_chrono(self) -> ChronoProgram:
        """Request the weekly schedule (``04``)."""
        data = await self._request(CMD_GET_CHRONO, CODE_CHRONO)
        try:
            self.chrono = parse_chrono(data)
        except ProtocolError as err:
            raise MczConnectionError(str(err)) from err
        return self.chrono

    async def write_chrono_day(self, day: int, slots: list[int]) -> None:
        """Write one day of the schedule."""
        await self._send(write_chrono_day(day, slots))

    async def set_clock(self, value: datetime) -> None:
        """Set the stove clock."""
        await self._send(set_datetime(value))

    async def write(self, param_id: int, value: int) -> None:
        """Send a ``WriteParametri`` command."""
        await self._send(write_parameter(param_id, value))

    async def _request(self, command: str, code: str) -> str:
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self._waiters.setdefault(code, []).append(future)
        try:
            await self._send(command)
            async with asyncio.timeout(RESPONSE_TIMEOUT):
                return await future
        except TimeoutError as err:
            raise MczTimeoutError(f"No answer to {command}") from err
        finally:
            waiters = self._waiters.get(code, [])
            if future in waiters:
                waiters.remove(future)

    async def _send(self, frame: str) -> None:
        if not self.connected:
            raise MczConnectionError("Not connected")
        assert self._ws is not None
        _LOGGER.debug("Sending %s", frame)
        async with self._send_lock:
            try:
                await self._ws.send_str(frame)
            except (aiohttp.ClientError, ConnectionError) as err:
                raise MczConnectionError(f"Send failed: {err}") from err

    async def _read_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        try:
            async for msg in ws:
                if msg.type is aiohttp.WSMsgType.TEXT:
                    await self._handle_frame(msg.data)
                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                    break
        except (aiohttp.ClientError, ConnectionError) as err:
            _LOGGER.debug("Read loop ended: %s", err)
        finally:
            # Only touch shared state if no newer connection replaced this one.
            if self._ws is ws:
                self._ws = None
                self._fail_waiters(MczConnectionError("Connection closed"))

    async def _handle_frame(self, frame: str) -> None:
        _LOGGER.debug("Received %s", frame)
        self.recent_frames.append(frame)
        if frame.startswith(CODE_PING):
            with contextlib.suppress(MczConnectionError):
                await self._send(CMD_PONG)
            return
        try:
            code, data = split_frame(frame)
        except ProtocolError:
            _LOGGER.debug("Ignoring malformed frame %r", frame)
            return
        for future in self._waiters.pop(code, []):
            if not future.done():
                future.set_result(data)

    def _fail_waiters(self, err: Exception) -> None:
        waiters, self._waiters = self._waiters, {}
        for futures in waiters.values():
            for future in futures:
                if not future.done():
                    future.set_exception(err)
