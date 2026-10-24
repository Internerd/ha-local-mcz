"""Diagnostics for the MCZ Maestro (local) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import MczConfigEntry

TO_REDACT = {CONF_HOST, "unique_id", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MczConfigEntry
) -> dict[str, Any]:
    """Return raw frames so protocol questions can be answered from a dump."""
    coordinator = entry.runtime_data
    client = coordinator.client
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "parameters": {
            "raw": client.parameters.raw if client.parameters else None,
            "bytes": client.parameters.values if client.parameters else None,
        },
        "info": {
            "raw": client.info.raw if client.info else None,
            "fields": client.info.fields if client.info else None,
        },
        "recent_frames": list(client.recent_frames),
    }
