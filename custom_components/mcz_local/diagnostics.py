"""Diagnostics for the MCZ Maestro (local) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import MczConfigEntry
from .protocol import CODE_VERSIONS

TO_REDACT = {CONF_HOST, "unique_id", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MczConfigEntry
) -> dict[str, Any]:
    """Return raw frames so protocol questions can be answered from a dump."""
    client = entry.runtime_data.client
    versions = client.versions
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
        # Serial number and MAC address are left out on purpose.
        "versions": {
            "panel_type": versions.panel_type,
            "panel_firmware": versions.panel_firmware,
            "field_count": len(versions.fields),
        }
        if versions
        else None,
        "alarms": [
            {"state": alarm.state, "time": alarm.time.isoformat()}
            for alarm in client.alarms or []
        ],
        "recent_frames": [
            f"{CODE_VERSIONS}|{REDACTED}"
            if frame.startswith(f"{CODE_VERSIONS}|")
            else frame
            for frame in client.recent_frames
        ],
    }
