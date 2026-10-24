"""Polling coordinator for the MCZ Maestro (local) integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import MczClient, MczConnectionError
from .const import DOMAIN, scan_interval
from .protocol import StoveInfo, StoveParameters

_LOGGER = logging.getLogger(__name__)

type MczConfigEntry = ConfigEntry[MczCoordinator]


@dataclass
class StoveData:
    """Snapshot handed to the entities."""

    parameters: StoveParameters
    info: StoveInfo


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

    async def _async_update_data(self) -> StoveData:
        try:
            if not self.client.connected:
                await self.client.connect()
            info = await self.client.fetch_info()
        except MczConnectionError as err:
            await self.client.disconnect()
            raise UpdateFailed(str(err)) from err
        assert self.client.parameters is not None
        return StoveData(parameters=self.client.parameters, info=info)

    async def async_write(self, param_id: int, value: int) -> None:
        """Send a write command and refresh the state right after."""
        try:
            if not self.client.connected:
                await self.client.connect()
            await self.client.write(param_id, value)
        except MczConnectionError as err:
            await self.client.disconnect()
            raise HomeAssistantError(
                f"Writing parameter {param_id} failed: {err}"
            ) from err
        await self.async_request_refresh()
