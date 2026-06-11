"""Vaillant VRC 700 integration for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import VaillantAuth, VRC700Client
from .const import CONF_BRAND, CONF_COUNTRY, DOMAIN, PLATFORMS
from .coordinator import VRC700Coordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a VRC 700 system from a config entry."""
    session = async_create_clientsession(hass)
    auth = VaillantAuth(
        session,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        brand=entry.data.get(CONF_BRAND, "vaillant"),
        country=entry.data.get(CONF_COUNTRY) or None,
    )
    client = VRC700Client(session, auth)
    coordinator = VRC700Coordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options (e.g. polling interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
