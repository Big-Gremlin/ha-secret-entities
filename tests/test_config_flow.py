"""Config and options flow tests."""
from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.secret_entities.const import (
    CONF_ICON,
    CONF_ID,
    CONF_NAME,
    CONF_SECRET,
    DOMAIN,
)


async def _setup(hass: HomeAssistant, entry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id]


class TestConfigFlow:
    async def test_user_creates_entry(self, hass: HomeAssistant):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY

    async def test_single_instance_only(self, hass: HomeAssistant, entry):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "single_instance_allowed"


class TestOptionsAdd:
    async def test_add_secret_creates_it(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "add"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_NAME: "Router", CONF_SECRET: "hunter2", CONF_ICON: "mdi:key"},
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        secrets = coordinator.secrets
        assert len(secrets) == 1
        sid = secrets[0][CONF_ID]
        assert coordinator.decrypt(sid) == "hunter2"

    async def test_add_rejects_empty_secret(self, hass: HomeAssistant, entry):
        await _setup(hass, entry)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "add"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_NAME: "Router", CONF_SECRET: ""}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {CONF_SECRET: "secret_required"}


class TestOptionsEditRemove:
    async def test_edit_value_reencrypts(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        sid = await coordinator.async_add_secret("Router", "old")

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "edit"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_ID: sid}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_NAME: "Router", CONF_SECRET: "new"}
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert coordinator.decrypt(sid) == "new"

    async def test_edit_blank_secret_keeps_value(
        self, hass: HomeAssistant, entry
    ):
        coordinator = await _setup(hass, entry)
        sid = await coordinator.async_add_secret("Router", "keepme")

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "edit"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_ID: sid}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_NAME: "Renamed"}
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert coordinator.get(sid)[CONF_NAME] == "Renamed"
        assert coordinator.decrypt(sid) == "keepme"

    async def test_remove_secret(self, hass: HomeAssistant, entry):
        coordinator = await _setup(hass, entry)
        sid = await coordinator.async_add_secret("Router", "v")

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "remove"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_ID: sid}
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert coordinator.get(sid) is None

    async def test_menu_hides_edit_remove_when_empty(
        self, hass: HomeAssistant, entry
    ):
        await _setup(hass, entry)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.MENU
        assert "edit" not in result["menu_options"]
        assert "remove" not in result["menu_options"]
