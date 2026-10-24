"""Polling coordinator for the MCZ Maestro (local) integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import MczClient, MczConnectionError, MczTimeoutError
from .const import ALARM_HISTORY_INTERVAL, DOMAIN, scan_interval
from .protocol import AlarmEntry, StoveInfo, StoveParameters, StoveVersions

_LOGGER = logging.getLogger(__name__)

type MczConfigEntry = ConfigEntry[MczCoordinator]


@dataclass
class StoveData:
    """Snapshot handed to the entities."""

    parameters: StoveParameters
    info: StoveInfo
    versions: StoveVersions | None
    alarms: list[AlarmEntry] | None


class MczCoordinator(DataUpdateCoordinator[StoveData]):
    """Polls ``RecuperoInfo`` and reconnects when the stove goes silent."""

    config_entry: MczConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MczConfigEntry,
        client: MczClient,
        interval_seconds: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=scan_interval(interval_seconds),
        )
        self.client = client
        self._alarms_fetched: datetime | None = None

    async def _async_update_data(self) -> StoveData:
        try:
            if not self.client.connected:
                await self.client.connect()
            info = await self.client.fetch_info()
            await self._async_update_alarms()
        except MczConnectionError as err:
            await self.client.disconnect()
            raise UpdateFailed(str(err)) from err
        assert self.client.parameters is not None
        return StoveData(
            parameters=self.client.parameters,
            info=info,
            versions=self.client.versions,
            alarms=self.client.alarms,
        )

    async def _async_update_alarms(self) -> None:
        """Refresh the alarm history now and then; it changes rarely."""
        now = dt_util.utcnow()
        if (
            self._alarms_fetched is not None
            and now - self._alarms_fetched < ALARM_HISTORY_INTERVAL
        ):
            return
        self._alarms_fetched = now
        try:
            await self.client.fetch_alarms()
        except MczTimeoutError:
            _LOGGER.debug("Stove did not answer the alarm history request")

    async def _async_command(self, command: Callable[[], Awaitable[None]]) -> None:
        try:
            if not self.client.connected:
                await self.client.connect()
            await command()
        except MczConnectionError as err:
            await self.client.disconnect()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err

    async def async_write(self, *writes: tuple[int, int]) -> None:
        """Send one or more WriteParametri commands, then refresh."""

        async def send() -> None:
            for param_id, value in writes:
                await self.client.write(param_id, value)

        await self._async_command(send)
        await self.async_request_refresh()

    async def async_set_clock(self, value: datetime) -> None:
        """Set the stove clock."""
        await self._async_command(lambda: self.client.set_clock(value))
