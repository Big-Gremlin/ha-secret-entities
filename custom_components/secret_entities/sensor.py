"""Sensor platform: one read-only entity per secret showing the ciphertext.

The state is the encrypted token. The plaintext and the encryption key are
never exposed here — open the entity and all you see is the encrypted value.
Use the ``secret_entities.decrypt`` service to get the real value back.
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ICON,
    CONF_ID,
    CONF_NAME,
    CONF_TOKEN,
    DOMAIN,
    SIGNAL_SECRETS_CHANGED,
)
from .coordinator import SecretEntitiesCoordinator

# Sensor states are capped at 255 characters by Home Assistant.
_STATE_MAX_LEN = 255


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SecretEntitiesCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _sync_entities() -> None:
        current_ids = {s[CONF_ID] for s in coordinator.secrets}
        new_ids = current_ids - known
        if new_ids:
            async_add_entities(
                [SecretEntity(coordinator, sid) for sid in new_ids]
            )
            known.update(new_ids)
        known.intersection_update(current_ids)

    _sync_entities()

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_SECRETS_CHANGED, _sync_entities)
    )


class SecretEntity(SensorEntity):
    """Read-only sensor whose state is the encrypted token of one secret."""

    _attr_has_entity_name = True
    _attr_name = None  # the device name carries it
    _attr_icon = "mdi:shield-key"
    _attr_should_poll = False  # state is pushed via dispatcher, never polled

    def __init__(
        self, coordinator: SecretEntitiesCoordinator, secret_id: str
    ) -> None:
        self._coordinator = coordinator
        self._secret_id = secret_id
        self._attr_unique_id = f"{DOMAIN}_{secret_id}"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_SECRETS_CHANGED, self._handle_change
            )
        )

    @property
    def device_info(self) -> DeviceInfo | None:
        secret = self._coordinator.get(self._secret_id)
        if secret is None:
            return None
        return DeviceInfo(
            identifiers={(DOMAIN, self._secret_id)},
            name=secret[CONF_NAME],
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Secret Entities",
        )

    @callback
    def _handle_change(self) -> None:
        if self._coordinator.get(self._secret_id) is not None:
            self.async_write_ha_state()
            return
        # Secret was removed -> tear down entity and its device.
        entity_registry = er.async_get(self.hass)
        if self.entity_id and entity_registry.async_get(self.entity_id):
            entity_registry.async_remove(self.entity_id)
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, self._secret_id)}
        )
        if device and not er.async_entries_for_device(entity_registry, device.id):
            device_registry.async_remove_device(device.id)

    @property
    def icon(self) -> str | None:
        secret = self._coordinator.get(self._secret_id)
        if secret and secret.get(CONF_ICON):
            return secret[CONF_ICON]
        return self._attr_icon

    @property
    def native_value(self) -> str | None:
        secret = self._coordinator.get(self._secret_id)
        if secret is None:
            return None
        token = secret[CONF_TOKEN]
        if len(token) > _STATE_MAX_LEN:
            # Too long for a sensor state; show a stable marker instead of
            # letting HA reject the state. The full token still lives in
            # storage and decrypt keeps working.
            return token[: _STATE_MAX_LEN - 1] + "…"
        return token

    @property
    def available(self) -> bool:
        return self._coordinator.get(self._secret_id) is not None
