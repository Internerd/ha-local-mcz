"""Constants for the MCZ Maestro (local) integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "mcz_local"

DEFAULT_PORT: Final = 81
DEFAULT_SCAN_INTERVAL: Final = 5
MIN_SCAN_INTERVAL: Final = 3
MAX_SCAN_INTERVAL: Final = 300

CONF_SCAN_INTERVAL: Final = "scan_interval"

MANUFACTURER: Final = "MCZ"


def scan_interval(seconds: int) -> timedelta:
    """Return the polling interval as timedelta."""
    return timedelta(seconds=seconds)
