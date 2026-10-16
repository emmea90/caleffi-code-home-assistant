"""Config flow for Caleffi CODE."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from .api import CaleffiApi, CaleffiApiError
from .const import API_URL, CONF_REFRESH_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)


class CaleffiCodeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a Caleffi CODE account."""

    VERSION = 3

    def __init__(self) -> None:
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                api = CaleffiApi(self.hass, API_URL, user_input[CONF_EMAIL])
                tokens = await api.async_login(user_input[CONF_PASSWORD])
            except CaleffiApiError as err:
                _LOGGER.warning(
                    "Caleffi CODE login failed (HTTP %s, code %s)",
                    err.status,
                    err.code,
                )
                errors["base"] = (
                    "invalid_auth"
                    if err.status in (400, 401, 403)
                    else "cannot_connect"
                )
            else:
                await self.async_set_unique_id(user_input[CONF_EMAIL].casefold())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Caleffi CODE ({user_input[CONF_EMAIL]})",
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_REFRESH_TOKEN: tokens["refresh_token"],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.FlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if self._reauth_entry is None:
            return self.async_abort(reason="reauth_failed")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                api = CaleffiApi(self.hass, API_URL, user_input[CONF_EMAIL])
                tokens = await api.async_login(user_input[CONF_PASSWORD])
            except CaleffiApiError as err:
                _LOGGER.warning(
                    "Caleffi CODE reauthentication failed (HTTP %s, code %s)",
                    err.status,
                    err.code,
                )
                errors["base"] = (
                    "invalid_auth"
                    if err.status in (400, 401, 403)
                    else "cannot_connect"
                )
            else:
                if user_input[CONF_EMAIL].casefold() != self._reauth_entry.data[
                    CONF_EMAIL
                ].casefold():
                    errors["base"] = "invalid_auth"
                else:
                    self.hass.config_entries.async_update_entry(
                        self._reauth_entry,
                        data={
                            **self._reauth_entry.data,
                            CONF_EMAIL: user_input[CONF_EMAIL],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                            CONF_REFRESH_TOKEN: tokens["refresh_token"],
                        },
                    )
                    await self.hass.config_entries.async_reload(
                        self._reauth_entry.entry_id
                    )
                    return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_EMAIL,
                        default=self._reauth_entry.data[CONF_EMAIL],
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
