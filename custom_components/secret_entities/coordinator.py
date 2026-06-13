"""Coordinator: encrypted secret storage, CRUD, and the decrypt service.

Plaintext is never stored. On add/update the value is encrypted immediately
and only the resulting token (ciphertext) and the per-secret key are kept.
The key lives in ``.storage`` and is never exposed through entity state,
attributes, the public API, or the decrypt response — only the *decrypted
value* leaves the integration, and only through the ``decrypt`` service.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import (
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from . import crypto
from .const import (
    ATTR_ENTITY_ID,
    ATTR_NAME,
    ATTR_SECRET_ID,
    ATTR_VALUE,
    CONF_ICON,
    CONF_ID,
    CONF_KEY,
    CONF_NAME,
    CONF_SECRETS,
    CONF_TOKEN,
    DOMAIN,
    SAVE_DELAY_SECONDS,
    SERVICE_DECRYPT,
    SIGNAL_SECRETS_CHANGED,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)
_UNSET: Any = object()

# Keys that are safe to hand out (everything except the encryption key).
_PUBLIC_KEYS = (CONF_ID, CONF_NAME, CONF_ICON, CONF_TOKEN)


class SecretEntitiesCoordinator:
    """Holds the encrypted secrets, persists them, owns the crypto."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}"
        )
        # secret_id -> {id, name, icon, token, key}
        self._secrets: dict[str, dict[str, Any]] = {}
        self._unsub_listeners: list = []

    # ------------------------------------------------------------------ API

    @property
    def secrets(self) -> list[dict[str, Any]]:
        """All secrets as public views (no key), sorted by name."""
        views = [self._public(s) for s in self._secrets.values()]
        return sorted(views, key=lambda s: s[CONF_NAME].casefold())

    def get(self, secret_id: str) -> dict[str, Any] | None:
        """Return the public view of one secret, or None."""
        secret = self._secrets.get(secret_id)
        return self._public(secret) if secret is not None else None

    async def async_initialize(self) -> None:
        """Load persisted secrets."""
        data = await self._store.async_load() or {}
        for raw in data.get(CONF_SECRETS) or []:
            try:
                sid = raw[CONF_ID]
                self._secrets[sid] = {
                    CONF_ID: sid,
                    CONF_NAME: raw[CONF_NAME],
                    CONF_ICON: raw.get(CONF_ICON),
                    CONF_TOKEN: raw[CONF_TOKEN],
                    CONF_KEY: raw[CONF_KEY],
                }
            except KeyError:
                _LOGGER.exception("Skipping malformed stored secret: %s", raw)

        self._unsub_listeners.append(
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, self._async_handle_stop
            )
        )

    async def async_shutdown(self) -> None:
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()
        await self._store.async_save(self._serialize())

    # ----------------------------------------------------------- mutations

    async def async_add_secret(
        self, name: str, secret: str, icon: str | None = None
    ) -> str:
        """Encrypt ``secret`` under a fresh key, store it, return the id."""
        key = crypto.generate_key()
        sid = uuid.uuid4().hex
        self._secrets[sid] = {
            CONF_ID: sid,
            CONF_NAME: name,
            CONF_ICON: icon or None,
            CONF_TOKEN: crypto.encrypt(key, secret),
            CONF_KEY: key,
        }
        await self._async_save_and_notify()
        return sid

    async def async_update_secret(
        self,
        secret_id: str,
        *,
        name: str | None = None,
        secret: str | None = None,
        icon: Any = _UNSET,
    ) -> None:
        """Update fields of a secret.

        Passing ``secret`` re-encrypts the value under a brand-new key
        (so the old key can never decrypt the new token). Leaving it out
        keeps the existing ciphertext untouched.
        """
        entry = self._secrets.get(secret_id)
        if entry is None:
            raise KeyError(secret_id)
        if name is not None:
            entry[CONF_NAME] = name
        if icon is not _UNSET:
            entry[CONF_ICON] = icon or None
        if secret is not None:
            key = crypto.generate_key()
            entry[CONF_KEY] = key
            entry[CONF_TOKEN] = crypto.encrypt(key, secret)
        await self._async_save_and_notify()

    async def async_remove_secret(self, secret_id: str) -> None:
        if self._secrets.pop(secret_id, None) is not None:
            self._cleanup_secret_registries(secret_id)
            await self._async_save_and_notify()

    @callback
    def _cleanup_secret_registries(self, secret_id: str) -> None:
        """Remove entity and device registry entries for a deleted secret.

        Disabled entities never receive SIGNAL_SECRETS_CHANGED and cannot
        clean themselves up, so the coordinator must do it centrally.
        """
        entity_reg = er.async_get(self.hass)
        device_reg = dr.async_get(self.hass)
        device = device_reg.async_get_device(identifiers={(DOMAIN, secret_id)})
        if device is None:
            return
        for entry in er.async_entries_for_device(
            entity_reg, device.id, include_disabled_entities=True
        ):
            entity_reg.async_remove(entry.entity_id)
        device_reg.async_remove_device(device.id)

    # ------------------------------------------------------------- decrypt

    def decrypt(self, secret_id: str) -> str:
        """Return the decrypted plaintext for ``secret_id``.

        Raises KeyError if unknown, crypto.InvalidToken if the stored token
        and key no longer match.
        """
        entry = self._secrets.get(secret_id)
        if entry is None:
            raise KeyError(secret_id)
        return crypto.decrypt(entry[CONF_KEY], entry[CONF_TOKEN])

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _public(secret: dict[str, Any]) -> dict[str, Any]:
        """Strip the encryption key from a secret before handing it out."""
        return {k: secret.get(k) for k in _PUBLIC_KEYS}

    def _serialize(self) -> dict[str, Any]:
        return {
            CONF_SECRETS: [
                {
                    CONF_ID: s[CONF_ID],
                    CONF_NAME: s[CONF_NAME],
                    CONF_ICON: s.get(CONF_ICON),
                    CONF_TOKEN: s[CONF_TOKEN],
                    CONF_KEY: s[CONF_KEY],
                }
                for s in self._secrets.values()
            ]
        }

    async def _async_save_and_notify(self) -> None:
        self._store.async_delay_save(self._serialize, SAVE_DELAY_SECONDS)
        async_dispatcher_send(self.hass, SIGNAL_SECRETS_CHANGED)

    async def _async_handle_stop(self, _event: Event) -> None:
        await self._store.async_save(self._serialize())


# ----------------------------------------------------------- service registration


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_DECRYPT):
        return

    async def _handle_decrypt(call: ServiceCall) -> ServiceResponse:
        secret_id: str | None = call.data.get(ATTR_SECRET_ID)
        entity_id: str | None = call.data.get(ATTR_ENTITY_ID)

        if secret_id is None and entity_id is None:
            raise ServiceValidationError("Provide either secret_id or entity_id")

        if secret_id is None:
            entity_reg = er.async_get(hass)
            entry = entity_reg.async_get(entity_id)
            if entry is None or not entry.unique_id.startswith(f"{DOMAIN}_"):
                raise ServiceValidationError(f"Entity {entity_id} is not a secret entity")
            secret_id = entry.unique_id[len(f"{DOMAIN}_"):]

        for coordinator in list(hass.data.get(DOMAIN, {}).values()):
            if coordinator.get(secret_id) is not None:
                try:
                    plaintext = coordinator.decrypt(secret_id)
                except crypto.InvalidToken as err:
                    raise ServiceValidationError(
                        f"Stored key does not match the token for {secret_id}"
                    ) from err
                return {
                    ATTR_SECRET_ID: secret_id,
                    ATTR_NAME: coordinator.get(secret_id)[CONF_NAME],
                    ATTR_VALUE: plaintext,
                }
        raise ServiceValidationError(f"No secret with id {secret_id}")

    schema = vol.Schema(
        {
            vol.Exclusive(ATTR_SECRET_ID, "identifier"): str,
            vol.Exclusive(ATTR_ENTITY_ID, "identifier"): str,
        }
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_DECRYPT,
        _handle_decrypt,
        schema=schema,
        supports_response=SupportsResponse.ONLY,
    )
