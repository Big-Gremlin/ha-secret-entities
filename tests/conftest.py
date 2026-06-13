"""Shared test fixtures."""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.secret_entities.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make Home Assistant load components from custom_components/ in tests."""
    yield


@pytest.fixture
def entry(hass):
    """Bare config entry — secrets live in storage, not options."""
    e = MockConfigEntry(domain=DOMAIN, data={}, options={}, unique_id=DOMAIN)
    e.add_to_hass(hass)
    return e


@pytest.fixture
async def setup_integration(hass, entry):
    """Set up the integration and return the coordinator."""
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]
