"""Read-only sensors for the Vaillant VRC 700 integration (Phase B).

Operating modes / setpoints become select & number entities in Phase C;
until then they are exposed as attributes of the System Status sensor so
everything is verifiable without future entity-ID churn.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfPressure, UnitOfTemperature, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VRC700Coordinator, VRC700Data
from .entity import VRC700Entity


@dataclass(frozen=True, kw_only=True)
class VRC700SensorDescription(SensorEntityDescription):
    value_fn: Callable[[VRC700Data], Any]
    attributes_fn: Callable[[VRC700Data], dict[str, Any]] | None = None


def _zone(data: VRC700Data):
    return data.system.primary_zone


def _circuit(data: VRC700Data):
    return data.system.primary_circuit


def _dhw(data: VRC700Data):
    return data.system.primary_dhw


def _status_attributes(data: VRC700Data) -> dict[str, Any]:
    s = data.system
    z, c, d = s.primary_zone, s.primary_circuit, s.primary_dhw
    return {
        "energy_manager_state": s.energy_manager_state,
        "circuit_state": c.state if c else None,
        "heating_mode": z.heating_mode if z else None,
        "heating_day_temperature": z.heating_day_temp if z else None,
        "heating_setback_temperature": z.heating_setback_temp if z else None,
        "cooling_mode": z.cooling_mode if z else None,
        "cooling_day_temperature": z.cooling_day_temp if z else None,
        "dhw_mode": d.mode if d else None,
        "dhw_setpoint": d.setpoint if d else None,
        "manual_cooling_days": s.manual_cooling_days,
        "manual_cooling_active": s.manual_cooling_active,
        "system_off": s.system_off,
        "controller": f"{s.controller_type} {s.controller_revision}",
    }


SENSORS: tuple[VRC700SensorDescription, ...] = (
    VRC700SensorDescription(
        key="system_status",
        translation_key="system_status",
        icon="mdi:heat-pump",
        value_fn=lambda d: d.system.system_status,
        attributes_fn=_status_attributes,
    ),
    VRC700SensorDescription(
        key="outside_temperature",
        translation_key="outside_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda d: d.system.outdoor_temperature,
    ),
    VRC700SensorDescription(
        key="outside_temperature_avg_24h",
        translation_key="outside_temperature_avg_24h",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.system.outdoor_temperature_avg24h,
    ),
    VRC700SensorDescription(
        key="indoor_temperature",
        translation_key="indoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda d: z.room_temperature if (z := _zone(d)) else None,
    ),
    VRC700SensorDescription(
        key="indoor_humidity",
        translation_key="indoor_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=lambda d: z.humidity if (z := _zone(d)) else None,
    ),
    VRC700SensorDescription(
        key="flow_temperature",
        translation_key="flow_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda d: c.flow_temperature if (c := _circuit(d)) else None,
    ),
    VRC700SensorDescription(
        key="water_pressure",
        translation_key="water_pressure",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        suggested_display_precision=1,
        value_fn=lambda d: d.system.water_pressure,
    ),
    VRC700SensorDescription(
        key="dhw_temperature",
        translation_key="dhw_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda d: w.current_temperature if (w := _dhw(d)) else None,
    ),
    VRC700SensorDescription(
        key="dhw_status",
        translation_key="dhw_status",
        icon="mdi:water-boiler",
        value_fn=lambda d: d.system.dhw_status,
        attributes_fn=lambda d: {
            "special_function": w.special_function if (w := _dhw(d)) else None,
            "setpoint": w.setpoint if (w := _dhw(d)) else None,
            "min_setpoint": w.min_setpoint if (w := _dhw(d)) else None,
            "max_setpoint": w.max_setpoint if (w := _dhw(d)) else None,
        },
    ),
    VRC700SensorDescription(
        key="error_codes",
        translation_key="error_codes",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: len(d.trouble_codes),
        attributes_fn=lambda d: {"codes": d.trouble_codes},
    ),
    VRC700SensorDescription(
        key="api_request_count",
        translation_key="api_request_count",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.request_count,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VRC700Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(VRC700Sensor(coordinator, desc) for desc in SENSORS)


class VRC700Sensor(VRC700Entity, SensorEntity):
    entity_description: VRC700SensorDescription

    def __init__(
        self, coordinator: VRC700Coordinator, description: VRC700SensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn:
            return self.entity_description.attributes_fn(self.coordinator.data)
        return None
