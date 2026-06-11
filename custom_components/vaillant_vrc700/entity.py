"""Base entity for the Vaillant VRC 700 integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import VRC700Coordinator


class VRC700Entity(CoordinatorEntity[VRC700Coordinator]):
    """All entities belong to one 'VRC700' device per system."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VRC700Coordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.system_id}_{key}"
        system = coordinator.data.system
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.system_id)},
            name="VRC700",
            manufacturer=MANUFACTURER,
            model=f"{system.controller_type or 'VRC700'} {system.controller_revision or ''}".strip(),
        )
