"""Force-refresh button for the Vaillant VRC 700 (requirement 8).

Rate-limited to one press per REFRESH_BUTTON_COOLDOWN seconds to protect
the API quota, and refuses to fire during a quota pause.
"""

from __future__ import annotations

import time

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, REFRESH_BUTTON_COOLDOWN
from .coordinator import VRC700Coordinator
from .entity import VRC700Entity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VRC700Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VRC700RefreshButton(coordinator)])


class VRC700RefreshButton(VRC700Entity, ButtonEntity):
    _attr_translation_key = "refresh"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: VRC700Coordinator) -> None:
        super().__init__(coordinator, "refresh")
        self._last_press = 0.0

    async def async_press(self) -> None:
        coordinator = self.coordinator
        if coordinator.quota_paused:
            raise HomeAssistantError(
                "myVAILLANT API quota is exhausted — refresh paused until "
                f"{coordinator.quota_paused_until:%H:%M:%S}"
            )
        now = time.monotonic()
        if now - self._last_press < REFRESH_BUTTON_COOLDOWN:
            wait = int(REFRESH_BUTTON_COOLDOWN - (now - self._last_press))
            raise HomeAssistantError(
                f"Refresh was pressed recently — wait {wait}s (quota protection)"
            )
        self._last_press = now
        coordinator.force_aux_fetch()
        await coordinator.async_request_refresh()
