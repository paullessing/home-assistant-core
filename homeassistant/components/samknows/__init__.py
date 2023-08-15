"""The SamKnows Whitebox integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .whitebox import WhiteboxApi

PLATFORMS: list[Platform] = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SamKnows Whitebox from a config entry."""

    username = entry.data["username"]
    password = entry.data["password"]

    _LOGGER.warning("Creating entry %s", username)

    hass.data.setdefault(DOMAIN, {})
    # TODO 1. Create API instance

    api = WhiteboxApi(username=username, password=password)

    # TODO 2. Validate the API connection (and authentication)

    result = await api.login()

    if result is False:
        _LOGGER.error("Failed to set up Whitebox API")
        return False

    # TODO 3. Store an API object for your platforms to access
    # hass.data[DOMAIN][entry.entry_id] = MyApi(...)
    hass.data[DOMAIN][entry.entry_id] = api

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
