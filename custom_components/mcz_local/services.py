"""Services for the MCZ Maestro (local) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import DOMAIN
from .coordinator import MczConfigEntry
from .protocol import CHRONO_DAYS, CHRONO_LEVELS, CHRONO_SLOTS

SERVICE_SET_CHRONO_DAY = "set_chrono_day"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_DAY = "day"
ATTR_PERIODS = "periods"


def _slot(value: Any) -> int:
    """Parse ``HH:MM`` on a half-hour boundary into a slot index 0..48."""
    try:
        hours, minutes = (int(part) for part in str(value).split(":")[:2])
    except ValueError as err:
        raise vol.Invalid(f"Invalid time {value!r}") from err
    if minutes not in (0, 30) or not 0 <= hours <= 24 or (hours == 24 and minutes):
        raise vol.Invalid(f"{value!r} must be a full or half hour (00:00-24:00)")
    return hours * 2 + minutes // 30


PERIOD_SCHEMA = vol.Schema(
    {
        vol.Required("from"): _slot,
        vol.Required("to"): _slot,
        vol.Required("level"): vol.All(vol.Coerce(int), vol.Range(1, CHRONO_LEVELS)),
    }
)

SET_CHRONO_DAY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_DAY): vol.All(vol.Coerce(int), vol.Range(0, CHRONO_DAYS - 1)),
        vol.Required(ATTR_PERIODS): vol.All(cv.ensure_list, [PERIOD_SCHEMA]),
    }
)


def build_slots(periods: list[dict[str, int]]) -> list[int]:
    """Turn periods into 48 slot levels; uncovered slots are off.

    ``to`` = 00:00 means midnight at the end of the day.
    """
    slots = [0] * CHRONO_SLOTS
    for period in periods:
        start, end = period["from"], period["to"] or CHRONO_SLOTS
        if start >= end:
            raise vol.Invalid("'from' must be before 'to'")
        slots[start:end] = [period["level"]] * (end - start)
    return slots


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services."""

    async def set_chrono_day(call: ServiceCall) -> None:
        entry: MczConfigEntry | None = hass.config_entries.async_get_entry(
            call.data[ATTR_CONFIG_ENTRY_ID]
        )
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_not_loaded"
            )
        try:
            slots = build_slots(call.data[ATTR_PERIODS])
        except vol.Invalid as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_periods",
                translation_placeholders={"error": str(err)},
            ) from err
        await entry.runtime_data.async_write_chrono_day(call.data[ATTR_DAY], slots)

    hass.services.async_register(
        DOMAIN, SERVICE_SET_CHRONO_DAY, set_chrono_day, schema=SET_CHRONO_DAY_SCHEMA
    )
