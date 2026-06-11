"""Binary sensors for the Vaillant VRC 700 integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VRC700Coordinator
from .entity import VRC700Entity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VRC700Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VRC700Online(coordinator), VRC700Problem(coordinator)])


class VRC700Online(VRC700Entity, BinarySensorEntity):
    """Requirement 6i — gateway online/offline."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "online"

    def __init__(self, coordinator: VRC700Coordinator) -> None:
        super().__init__(coordinator, "online")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.connected


class VRC700Problem(VRC700Entity, BinarySensorEntity):
    """Requirement 6a — any active trouble codes."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "problem"

    def __init__(self, coordinator: VRC700Coordinator) -> None:
        super().__init__(coordinator, "problem")

    @property
    def is_on(self) -> bool:
        return len(self.coordinator.data.trouble_codes) > 0

    @property
    def extra_state_attributes(self) -> dict:
        return {"codes": self.coordinator.data.trouble_codes}
