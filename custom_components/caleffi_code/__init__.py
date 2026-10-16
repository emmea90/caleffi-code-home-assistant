"""Caleffi CODE integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval

from .api import CaleffiApi, CaleffiApiError
from .const import (
    API_URL,
    CONF_EMAIL,
    CONF_REFRESH_TOKEN,
    DOMAIN,
    REAUTH_INTERVAL_MINUTES,
)
from .coordinator import CaleffiCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Drop the API URL, which is now fixed, from existing entries."""
    if entry.version > 3:
        return False

    if entry.version < 3:
        data = {k: v for k, v in entry.data.items() if k != "api_url"}
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            options={},
            unique_id=entry.data[CONF_EMAIL].casefold(),
            version=3,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    def save_refresh_token(refresh_token: str) -> None:
        if entry.data.get(CONF_REFRESH_TOKEN) != refresh_token:
            hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_REFRESH_TOKEN: refresh_token},
            )

    api = CaleffiApi(
        hass=hass,
        base_url=API_URL,
        email=entry.data[CONF_EMAIL],
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        password=entry.data.get(CONF_PASSWORD),
        on_refresh_token=save_refresh_token,
    )
    try:
        await api.async_reauthenticate()
    except CaleffiApiError as err:
        if err.status in (400, 401, 403):
            raise ConfigEntryAuthFailed("Caleffi CODE authentication failed") from err
        raise ConfigEntryNotReady("Cannot connect to the Caleffi CODE API") from err

    if not entry.data.get(CONF_PASSWORD):
        _LOGGER.warning(
            "Caleffi CODE password is not stored. Complete the reauthentication "
            "prompt once so an expired session can be renewed automatically"
        )
        entry.async_start_reauth(hass)

    async def _async_keepalive(_now: datetime) -> None:
        try:
            await api.async_reauthenticate()
        except CaleffiApiError as err:
            if err.status in (400, 401, 403):
                _LOGGER.error("Caleffi CODE session expired and could not be renewed")
                entry.async_start_reauth(hass)
                return
            _LOGGER.warning("Caleffi CODE session renewal failed: %s", err)

    entry.async_on_unload(
        async_track_time_interval(
            hass,
            _async_keepalive,
            timedelta(minutes=REAUTH_INTERVAL_MINUTES),
        )
    )

    coordinator = CaleffiCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
