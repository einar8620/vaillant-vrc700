"""Switches for the Vaillant VRC 700 (requirements 4, 5).

- Manual Cooling: POST/DELETE cooling-for-days, days from the number entity
- Hot Water Boost: POST/DELETE cylinder boost; the API has no duration, so
  the integration auto-cancels after the configured time (default 30 min).
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import CONF_BOOST_DURATION, DEFAULT_BOOST_DURATION, DOMAIN
from .coordinator import VRC700Coordinator
from .entity import VRC700Entity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VRC700Coordinator = hass.data[DOMAIN][entry.entry_id]
    boost_minutes = entry.options.get(CONF_BOOST_DURATION, DEFAULT_BOOST_DURATION)
    async_add_entities(
        [
            VRC700ManualCooling(coordinator),
            VRC700HotWaterBoost(coordinator, boost_minutes),
        ]
    )


class VRC700ManualCooling(VRC700Entity, SwitchEntity):
    """Requirement 4 — manual cooling for N days."""

    _attr_translation_key = "manual_cooling"
    _attr_icon = "mdi:snowflake-check"

    def __init__(self, coordinator: VRC700Coordinator) -> None:
        super().__init__(coordinator, "manual_cooling")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.system.manual_cooling_active

    @property
    def extra_state_attributes(self) -> dict:
        return {"days": self.coordinator.data.system.manual_cooling_days}

    async def async_turn_on(self, **kwargs) -> None:
        coordinator = self.coordinator
        days = coordinator.manual_cooling_days_setting

        def mutate(data) -> None:
            data.system.manual_cooling_days = days

        await coordinator.async_write(
            coordinator.client.start_manual_cooling(coordinator.system_id, days),
            mutate,
        )

    async def async_turn_off(self, **kwargs) -> None:
        coordinator = self.coordinator

        def mutate(data) -> None:
            data.system.manual_cooling_days = 0

        await coordinator.async_write(
            coordinator.client.stop_manual_cooling(coordinator.system_id),
            mutate,
        )


class VRC700HotWaterBoost(VRC700Entity, SwitchEntity):
    """Requirement 5 — cylinder boost with integration-side auto-off timer."""

    _attr_translation_key = "hot_water_boost"
    _attr_icon = "mdi:water-boiler-alert"

    def __init__(self, coordinator: VRC700Coordinator, boost_minutes: int) -> None:
        super().__init__(coordinator, "hot_water_boost")
        self._boost_minutes = boost_minutes
        self._cancel_timer = None

    @property
    def is_on(self) -> bool:
        dhw = self.coordinator.data.system.primary_dhw
        return bool(dhw and dhw.special_function == "CYLINDER_BOOST")

    @property
    def extra_state_attributes(self) -> dict:
        return {"auto_off_minutes": self._boost_minutes}

    def _dhw_index(self) -> int:
        dhw = self.coordinator.data.system.primary_dhw
        return dhw.index if dhw else 255

    def _cancel_auto_off(self) -> None:
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None

    async def async_turn_on(self, **kwargs) -> None:
        coordinator = self.coordinator

        def mutate(data) -> None:
            if data.system.primary_dhw:
                data.system.primary_dhw.special_function = "CYLINDER_BOOST"

        def verify(data) -> bool:
            dhw = data.system.primary_dhw
            return bool(dhw and dhw.special_function == "CYLINDER_BOOST")

        await coordinator.async_write(
            coordinator.client.start_dhw_boost(
                coordinator.system_id, dhw_index=self._dhw_index()
            ),
            mutate,
            verify=verify,
        )
        self._cancel_auto_off()
        self._cancel_timer = async_call_later(
            self.hass, timedelta(minutes=self._boost_minutes), self._auto_off
        )

    async def _auto_off(self, _now) -> None:
        self._cancel_timer = None
        if self.is_on:
            _LOGGER.info(
                "Hot water boost auto-off after %s minutes", self._boost_minutes
            )
            await self.async_turn_off()

    async def async_turn_off(self, **kwargs) -> None:
        self._cancel_auto_off()
        coordinator = self.coordinator

        def mutate(data) -> None:
            if data.system.primary_dhw:
                data.system.primary_dhw.special_function = "NONE"

        def verify(data) -> bool:
            dhw = data.system.primary_dhw
            return bool(dhw and dhw.special_function != "CYLINDER_BOOST")

        await coordinator.async_write(
            coordinator.client.stop_dhw_boost(
                coordinator.system_id, dhw_index=self._dhw_index()
            ),
            mutate,
            verify=verify,
        )

    async def async_will_remove_from_hass(self) -> None:
        self._cancel_auto_off()
        await super().async_will_remove_from_hass()
