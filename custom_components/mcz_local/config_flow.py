"""Config flow for the MCZ Maestro (local) integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .client import MczClient, MczConnectionError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TITLE,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import MczConfigEntry

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
    }
)


async def _async_validate(
    hass: HomeAssistant, host: str, port: int
) -> tuple[str | None, str]:
    """Connect once; return (error key, unique id).

    The unique id is the module serial, or host:port if the stove did not
    report one.
    """
    client = MczClient(async_get_clientsession(hass), host, port)
    try:
        await client.connect()
    except MczConnectionError:
        return "cannot_connect", ""
    except Exception:
        _LOGGER.exception("Unexpected error while connecting")
        return "unknown", ""
    finally:
        await client.close()
    serial = client.versions.serial if client.versions else None
    return None, serial or f"{host}:{port}"


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    return {CONF_HOST: user_input[CONF_HOST].strip(), CONF_PORT: user_input[CONF_PORT]}


class MczConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for host and port and check that the stove answers."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input)
            self._async_abort_entries_match(data)
            error, unique_id = await _async_validate(self.hass, **data)
            if error is None:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(updates=data)
                return self.async_create_entry(title=DEFAULT_TITLE, data=data)
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change host or port of an existing stove, e.g. after an IP change."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input)
            error, unique_id = await _async_validate(self.hass, **data)
            if error is None:
                await self.async_set_unique_id(unique_id)
                if unique_id != entry.unique_id:
                    # A different stove (or one without serial) must not
                    # replace an entry that is already configured.
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    entry, unique_id=unique_id, data_updates=data
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: MczConfigEntry) -> MczOptionsFlow:
        """Return the options flow."""
        return MczOptionsFlow()


class MczOptionsFlow(OptionsFlowWithReload):
    """Polling interval option."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
