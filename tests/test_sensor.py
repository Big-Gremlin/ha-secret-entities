"""Tests for the secret sensor entities."""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.secret_entities.const import CONF_TOKEN, DOMAIN


async def _setup(hass: HomeAssistant, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


def _state_for(hass, coordinator, sid):
    """Find the HA state object for the sensor of secret ``sid``."""
    unique = f"{DOMAIN}_{sid}"
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(hass)
    entity_id = reg.async_get_entity_id("sensor", DOMAIN, unique)
    return hass.states.get(entity_id) if entity_id else None


async def test_entity_state_is_ciphertext(hass: HomeAssistant, entry):
    coordinator = await _setup(hass, entry)
    sid = await coordinator.async_add_secret("Router", "hunter2")
    await hass.async_block_till_done()

    state = _state_for(hass, coordinator, sid)
    assert state is not None
    # State equals the stored token, and reveals neither plaintext nor key.
    assert state.state == coordinator.get(sid)[CONF_TOKEN]
    assert "hunter2" not in state.state
    assert coordinator._secrets[sid]["key"] not in state.state
    # And no attribute leaks the secret.
    blob = repr(state.attributes)
    assert "hunter2" not in blob
    assert coordinator._secrets[sid]["key"] not in blob


async def test_entity_created_at_runtime(hass: HomeAssistant, entry):
    coordinator = await _setup(hass, entry)
    sid = await coordinator.async_add_secret("Later", "v")
    await hass.async_block_till_done()
    assert _state_for(hass, coordinator, sid) is not None


async def test_entity_removed_with_secret(hass: HomeAssistant, entry):
    coordinator = await _setup(hass, entry)
    sid = await coordinator.async_add_secret("Temp", "v")
    await hass.async_block_till_done()
    assert _state_for(hass, coordinator, sid) is not None

    await coordinator.async_remove_secret(sid)
    await hass.async_block_till_done()
    assert _state_for(hass, coordinator, sid) is None
