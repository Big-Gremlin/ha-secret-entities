"""Integration tests for SecretEntitiesCoordinator and the decrypt service."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.secret_entities.const import (
    ATTR_NAME,
    ATTR_SECRET_ID,
    ATTR_VALUE,
    CONF_ICON,
    CONF_KEY,
    CONF_NAME,
    CONF_TOKEN,
    DOMAIN,
    SERVICE_DECRYPT,
)


async def _setup(hass: HomeAssistant, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestSecretCrud:
    async def test_add_secret_returns_id(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        sid = await coordinator.async_add_secret("Router", "hunter2")
        assert coordinator.get(sid)[CONF_NAME] == "Router"

    async def test_add_secret_does_not_store_plaintext(
        self, hass: HomeAssistant, entry
    ):
        coordinator = await _setup(hass, entry)
        sid = await coordinator.async_add_secret("Router", "hunter2")
        view = coordinator.get(sid)
        assert "hunter2" not in view[CONF_TOKEN]
        # The public view never carries the encryption key.
        assert CONF_KEY not in view

    async def test_decrypt_returns_plaintext(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        sid = await coordinator.async_add_secret("Router", "hunter2")
        assert coordinator.decrypt(sid) == "hunter2"

    async def test_remove_secret(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        sid = await coordinator.async_add_secret("x", "v")
        await coordinator.async_remove_secret(sid)
        assert coordinator.get(sid) is None

    async def test_update_name_keeps_value(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        sid = await coordinator.async_add_secret("old", "v")
        token_before = coordinator.get(sid)[CONF_TOKEN]

        await coordinator.async_update_secret(sid, name="new")

        assert coordinator.get(sid)[CONF_NAME] == "new"
        assert coordinator.get(sid)[CONF_TOKEN] == token_before
        assert coordinator.decrypt(sid) == "v"

    async def test_update_value_reencrypts_with_new_key(
        self, hass: HomeAssistant, entry
    ):
        coordinator = await _setup(hass, entry)
        sid = await coordinator.async_add_secret("x", "old-value")
        old_key = coordinator._secrets[sid][CONF_KEY]
        old_token = coordinator.get(sid)[CONF_TOKEN]

        await coordinator.async_update_secret(sid, secret="new-value")

        assert coordinator._secrets[sid][CONF_KEY] != old_key
        assert coordinator.get(sid)[CONF_TOKEN] != old_token
        assert coordinator.decrypt(sid) == "new-value"

    async def test_secrets_sorted_by_name(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        await coordinator.async_add_secret("Zeta", "v")
        await coordinator.async_add_secret("alpha", "v")
        assert [s[CONF_NAME] for s in coordinator.secrets] == ["alpha", "Zeta"]

    async def test_update_unknown_raises(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        with pytest.raises(KeyError):
            await coordinator.async_update_secret("nope", name="x")

    async def test_decrypt_unknown_raises(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        with pytest.raises(KeyError):
            coordinator.decrypt("nope")

    async def test_remove_nonexistent_is_noop(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        await coordinator.async_remove_secret("ghost")  # must not raise

    async def test_remove_secret_cleans_up_disabled_device(
        self, hass: HomeAssistant, entry
    ):
        """Deleting a secret whose entity is disabled must still remove the
        entity and device registry entries (disabled entities are never loaded
        into hass and never receive SIGNAL_SECRETS_CHANGED)."""
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers import entity_registry as er
        from homeassistant.helpers.entity_registry import RegistryEntryDisabler

        coordinator = await _setup(hass, entry)
        sid = await coordinator.async_add_secret("doomed", "s3cr3t")
        await hass.async_block_till_done()

        entity_reg = er.async_get(hass)
        device_reg = dr.async_get(hass)
        device = device_reg.async_get_device(identifiers={("secret_entities", sid)})
        assert device is not None

        # Disable the entity (simulates user disabling the device/entity).
        for entry_item in er.async_entries_for_device(entity_reg, device.id):
            entity_reg.async_update_entity(
                entry_item.entity_id, disabled_by=RegistryEntryDisabler.USER
            )
        await hass.async_block_till_done()

        # Delete the secret — coordinator must clean up registry despite no live listeners.
        await coordinator.async_remove_secret(sid)
        await hass.async_block_till_done()

        assert device_reg.async_get_device(identifiers={("secret_entities", sid)}) is None
        assert (
            er.async_entries_for_device(entity_reg, device.id, include_disabled_entities=True)
            == []
        )


# ---------------------------------------------------------------------------
# decrypt service
# ---------------------------------------------------------------------------


class TestDecryptService:
    async def test_service_returns_plaintext(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        sid = await coordinator.async_add_secret("Router", "hunter2")

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_DECRYPT,
            {ATTR_SECRET_ID: sid},
            blocking=True,
            return_response=True,
        )

        assert response[ATTR_VALUE] == "hunter2"
        assert response[ATTR_NAME] == "Router"
        assert response[ATTR_SECRET_ID] == sid

    async def test_service_unknown_secret_raises(
        self, hass: HomeAssistant, entry
    ):
        await _setup(hass, entry)
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_DECRYPT,
                {ATTR_SECRET_ID: "no-such-id"},
                blocking=True,
                return_response=True,
            )

    async def test_service_decrypt_by_entity_id(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        sid = await coordinator.async_add_secret("Router", "hunter2")
        await hass.async_block_till_done()

        # Derive the entity_id from state machine (sensor platform creates it).
        sensor_states = [
            s for s in hass.states.async_all() if s.entity_id.startswith("sensor.")
        ]
        assert len(sensor_states) == 1
        entity_id = sensor_states[0].entity_id

        from custom_components.secret_entities.const import ATTR_ENTITY_ID

        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_DECRYPT,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
            return_response=True,
        )

        assert response[ATTR_VALUE] == "hunter2"
        assert response[ATTR_NAME] == "Router"
        assert response[ATTR_SECRET_ID] == sid

    async def test_service_decrypt_unknown_entity_raises(
        self, hass: HomeAssistant, entry
    ):
        await _setup(hass, entry)
        from custom_components.secret_entities.const import ATTR_ENTITY_ID

        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_DECRYPT,
                {ATTR_ENTITY_ID: "sensor.does_not_exist"},
                blocking=True,
                return_response=True,
            )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    async def test_stored_secret_is_loaded(self, hass: HomeAssistant, entry):
        from custom_components.secret_entities import crypto

        key = crypto.generate_key()
        token = crypto.encrypt(key, "stored-value")
        stored = {
            "secrets": [
                {
                    "id": "abc",
                    "name": "stored",
                    "icon": "mdi:key",
                    "token": token,
                    "key": key,
                }
            ]
        }

        with patch(
            "custom_components.secret_entities.coordinator.Store"
        ) as MockStore:
            inst = MagicMock()
            inst.async_load = AsyncMock(return_value=stored)
            inst.async_delay_save = MagicMock()
            inst.async_save = AsyncMock()
            MockStore.return_value = inst

            coordinator = await _setup(hass, entry)

        assert coordinator.get("abc")[CONF_NAME] == "stored"
        assert coordinator.get("abc")[CONF_ICON] == "mdi:key"
        assert coordinator.decrypt("abc") == "stored-value"

    async def test_malformed_stored_secret_is_skipped(
        self, hass: HomeAssistant, entry
    ):
        from custom_components.secret_entities import crypto

        key = crypto.generate_key()
        stored = {
            "secrets": [
                {"id": "bad"},  # missing token/key/name
                {
                    "id": "good",
                    "name": "ok",
                    "token": crypto.encrypt(key, "v"),
                    "key": key,
                },
            ]
        }

        with patch(
            "custom_components.secret_entities.coordinator.Store"
        ) as MockStore:
            inst = MagicMock()
            inst.async_load = AsyncMock(return_value=stored)
            inst.async_delay_save = MagicMock()
            inst.async_save = AsyncMock()
            MockStore.return_value = inst

            coordinator = await _setup(hass, entry)

        assert coordinator.get("bad") is None
        assert coordinator.get("good") is not None
