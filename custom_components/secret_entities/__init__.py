"""Secret Entities - store encrypted secrets, decrypt them on demand."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, SERVICE_DECRYPT, STORAGE_KEY, STORAGE_VERSION
from .coordinator import SecretEntitiesCoordinator, _async_register_services

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = SecretEntitiesCoordinator(hass, entry)
    await coordinator.async_initialize()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    coordinator: SecretEntitiesCoordinator | None = hass.data[DOMAIN].pop(
        entry.entry_id, None
    )
    if coordinator is not None:
        await coordinator.async_shutdown()

    if not hass.data[DOMAIN] and hass.services.has_service(DOMAIN, SERVICE_DECRYPT):
        hass.services.async_remove(DOMAIN, SERVICE_DECRYPT)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
    await store.async_remove()
