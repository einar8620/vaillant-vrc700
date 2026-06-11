"""Diagnostics for the Vaillant VRC 700 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import VRC700Coordinator

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, "system_id", "systemId", "serialNumber"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: VRC700Coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "quota": {
            "paused": coordinator.quota_paused,
            "paused_until": str(coordinator.quota_paused_until),
            "request_count": coordinator.client.request_count,
        },
        "connected": data.connected if data else None,
        "trouble_codes": data.trouble_codes if data else None,
        "raw_system": async_redact_data(data.system.raw, TO_REDACT) if data else None,
    }
