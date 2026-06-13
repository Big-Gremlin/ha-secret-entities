"""Config flow for Secret Entities."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_ICON,
    CONF_ID,
    CONF_NAME,
    CONF_SECRET,
    DOMAIN,
)
from .coordinator import SecretEntitiesCoordinator

_PASSWORD_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)


class SecretEntitiesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial configuration flow - single instance."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Secret Entities", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SecretEntitiesOptionsFlow(config_entry)


class SecretEntitiesOptionsFlow(OptionsFlow):
    """Manage secrets: add, edit, remove."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        # Stored under a private name so we don't shadow the ``config_entry``
        # property that newer Home Assistant versions provide automatically.
        self._entry = config_entry
        self._edit_secret_id: str | None = None

    @property
    def _coordinator(self) -> SecretEntitiesCoordinator:
        return self.hass.data[DOMAIN][self._entry.entry_id]

    # -------------------------------------------------------------- menu

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        options = ["add"]
        if self._coordinator.secrets:
            options.extend(["edit", "remove"])
        return self.async_show_menu(step_id="init", menu_options=options)

    # --------------------------------------------------------------- add

    async def async_step_add(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            secret = user_input[CONF_SECRET]
            if not name:
                errors[CONF_NAME] = "name_required"
            elif not secret:
                errors[CONF_SECRET] = "secret_required"
            else:
                await self._coordinator.async_add_secret(
                    name=name,
                    secret=secret,
                    icon=user_input.get(CONF_ICON) or None,
                )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="add",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): selector.TextSelector(),
                    vol.Required(CONF_SECRET): _PASSWORD_SELECTOR,
                    vol.Optional(CONF_ICON): selector.IconSelector(),
                }
            ),
            errors=errors,
        )

    # -------------------------------------------------------------- edit

    async def async_step_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        secrets = self._coordinator.secrets
        if not secrets:
            return self.async_abort(reason="no_secrets")
        if user_input is not None:
            self._edit_secret_id = user_input[CONF_ID]
            return await self.async_step_edit_form()
        return self.async_show_form(
            step_id="edit",
            data_schema=_select_schema(secrets),
        )

    async def async_step_edit_form(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        assert self._edit_secret_id is not None
        secret = self._coordinator.get(self._edit_secret_id)
        if secret is None:
            return self.async_abort(reason="unknown_secret")

        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            else:
                # Empty secret field -> keep the existing ciphertext.
                new_secret = user_input.get(CONF_SECRET) or None
                await self._coordinator.async_update_secret(
                    self._edit_secret_id,
                    name=name,
                    secret=new_secret,
                    icon=user_input.get(CONF_ICON) or None,
                )
                return self.async_create_entry(title="", data={})

        icon = secret.get(CONF_ICON)
        icon_field = (
            vol.Optional(CONF_ICON, default=icon)
            if icon
            else vol.Optional(CONF_ICON)
        )
        return self.async_show_form(
            step_id="edit_form",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=secret[CONF_NAME]): (
                        selector.TextSelector()
                    ),
                    vol.Optional(CONF_SECRET): _PASSWORD_SELECTOR,
                    icon_field: selector.IconSelector(),
                }
            ),
            errors=errors,
            description_placeholders={"name": secret[CONF_NAME]},
        )

    # ------------------------------------------------------------ remove

    async def async_step_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        secrets = self._coordinator.secrets
        if not secrets:
            return self.async_abort(reason="no_secrets")
        if user_input is not None:
            await self._coordinator.async_remove_secret(user_input[CONF_ID])
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="remove",
            data_schema=_select_schema(secrets),
        )


def _select_schema(secrets: list[dict[str, Any]]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_ID): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=s[CONF_ID], label=s[CONF_NAME]
                        )
                        for s in secrets
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        }
    )
