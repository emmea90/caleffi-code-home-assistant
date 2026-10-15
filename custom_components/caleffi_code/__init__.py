"""Caleffi CODE integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import CaleffiApi, CaleffiApiError
from .const import API_URL, CONF_EMAIL, CONF_REFRESH_TOKEN, DOMAIN
from .coordinator import CaleffiCoordinator

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
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        on_refresh_token=save_refresh_token,
    )
    try:
        await api.async_refresh_access_token()
    except CaleffiApiError as err:
        if err.status in (400, 401, 403):
            raise ConfigEntryAuthFailed("Caleffi CODE refresh token is invalid") from err
        raise ConfigEntryNotReady("Cannot connect to the Caleffi CODE API") from err

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
