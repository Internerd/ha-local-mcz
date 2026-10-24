"""Fixtures for the MCZ Maestro (local) tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mcz_local.const import DOMAIN

from .fake_stove import FakeStove


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the integration from custom_components."""


@pytest.fixture
async def fake_stove(
    aiohttp_server, socket_enabled
) -> AsyncGenerator[tuple[FakeStove, int]]:
    """Run a fake stove on localhost and return it with its port."""
    stove = FakeStove()
    server = await aiohttp_server(stove.app)
    yield stove, server.port
    await stove.close()
    await server.close()


@pytest.fixture
def config_entry(fake_stove: tuple[FakeStove, int]) -> MockConfigEntry:
    """Return a config entry pointing at the fake stove."""
    _, port = fake_stove
    return MockConfigEntry(
        domain=DOMAIN,
        title="MCZ Maestro (127.0.0.1)",
        unique_id=f"127.0.0.1:{port}",
        data={"host": "127.0.0.1", "port": port},
    )
