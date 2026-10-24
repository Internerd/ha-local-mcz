"""Config flow tests."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mcz_local.const import DOMAIN

from .fake_stove import FakeStove


async def test_user_flow(
    hass: HomeAssistant, fake_stove: tuple[FakeStove, int]
) -> None:
    """A reachable stove creates an entry."""
    _, port = fake_stove
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": port}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"host": "127.0.0.1", "port": port}


async def test_user_flow_cannot_connect(hass: HomeAssistant, socket_enabled) -> None:
    """An unreachable stove shows an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": 1}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow(hass: HomeAssistant, fake_stove, config_entry) -> None:
    """The polling interval can be changed."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 10}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {"scan_interval": 10}


async def test_user_flow_duplicate(
    hass: HomeAssistant, fake_stove: tuple[FakeStove, int], config_entry
) -> None:
    """The same host and port can only be added once."""
    config_entry.add_to_hass(hass)
    _, port = fake_stove
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": " 127.0.0.1 ", "port": port}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure(
    hass: HomeAssistant, fake_stove: tuple[FakeStove, int], socket_enabled
) -> None:
    """A changed IP address can be entered without removing the entry."""
    _, port = fake_stove
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="MCZ Maestro",
        unique_id="10.0.0.99:81",
        data={"host": "10.0.0.99", "port": 81},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": 1}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": port}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {"host": "127.0.0.1", "port": port}
    assert entry.unique_id == f"127.0.0.1:{port}"
