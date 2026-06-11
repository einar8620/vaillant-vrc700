"""Operating mode selects for the Vaillant VRC 700 (requirements 2a, 3a).

Heating: Auto / Day / Set-back / Off
Cooling: Auto / Day / Off
Hot water: Auto / Day / Off
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VRC700Coordinator
from .entity import VRC700Entity

# HA option (lowercase, translated) <-> API value
HEATING_OPTIONS = {"auto": "AUTO", "day": "DAY", "set_back": "SET_BACK", "off": "OFF"}
COOLING_OPTIONS = {"auto": "AUTO", "day": "DAY", "off": "OFF"}
DHW_OPTIONS = {"auto": "AUTO", "day": "DAY", "off": "OFF"}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VRC700Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            VRC700HeatingMode(coordinator),
            VRC700CoolingMode(coordinator),
            VRC700DHWMode(coordinator),
        ]
    )


class VRC700ModeSelect(VRC700Entity, SelectEntity):
    """Base for the three mode selects."""

    _option_map: dict[str, str] = {}

    def __init__(self, coordinator: VRC700Coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_options = list(self._option_map)

    def _api_mode(self) -> str | None:
        raise NotImplementedError

    @property
    def current_option(self) -> str | None:
        api_value = self._api_mode()
        for option, value in self._option_map.items():
            if value == api_value:
                return option
        return None


class VRC700HeatingMode(VRC700ModeSelect):
    _attr_translation_key = "heating_mode"
    _option_map = HEATING_OPTIONS
    _attr_icon = "mdi:radiator"

    def __init__(self, coordinator: VRC700Coordinator) -> None:
        super().__init__(coordinator, "heating_mode")

    def _api_mode(self) -> str | None:
        zone = self.coordinator.data.system.primary_zone
        return zone.heating_mode if zone else None

    async def async_select_option(self, option: str) -> None:
        mode = self._option_map[option]
        coordinator = self.coordinator

        def mutate(data) -> None:
            if data.system.primary_zone:
                data.system.primary_zone.heating_mode = mode

        await coordinator.async_write(
            coordinator.client.set_heating_operation_mode(coordinator.system_id, mode),
            mutate,
        )


class VRC700CoolingMode(VRC700ModeSelect):
    _attr_translation_key = "cooling_mode"
    _option_map = COOLING_OPTIONS
    _attr_icon = "mdi:snowflake"

    def __init__(self, coordinator: VRC700Coordinator) -> None:
        super().__init__(coordinator, "cooling_mode")

    def _api_mode(self) -> str | None:
        zone = self.coordinator.data.system.primary_zone
        return zone.cooling_mode if zone else None

    async def async_select_option(self, option: str) -> None:
        mode = self._option_map[option]
        coordinator = self.coordinator

        def mutate(data) -> None:
            if data.system.primary_zone:
                data.system.primary_zone.cooling_mode = mode

        await coordinator.async_write(
            coordinator.client.set_cooling_operation_mode(coordinator.system_id, mode),
            mutate,
        )


class VRC700DHWMode(VRC700ModeSelect):
    _attr_translation_key = "dhw_mode"
    _option_map = DHW_OPTIONS
    _attr_icon = "mdi:water-boiler"

    def __init__(self, coordinator: VRC700Coordinator) -> None:
        super().__init__(coordinator, "dhw_mode")

    def _api_mode(self) -> str | None:
        dhw = self.coordinator.data.system.primary_dhw
        return dhw.mode if dhw else None

    async def async_select_option(self, option: str) -> None:
        mode = self._option_map[option]
        coordinator = self.coordinator
        dhw = coordinator.data.system.primary_dhw
        dhw_index = dhw.index if dhw else 255

        def mutate(data) -> None:
            if data.system.primary_dhw:
                data.system.primary_dhw.mode = mode

        await coordinator.async_write(
            coordinator.client.set_dhw_operation_mode(
                coordinator.system_id, mode, dhw_index=dhw_index
            ),
            mutate,
        )
