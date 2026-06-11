"""Temperature / duration numbers for the Vaillant VRC 700.

Requirements 2b, 2c, 3b, 4 (days), 6h-ii.
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VRC700Coordinator
from .entity import VRC700Entity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VRC700Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            VRC700HeatingDayTemp(coordinator),
            VRC700HeatingSetbackTemp(coordinator),
            VRC700CoolingDayTemp(coordinator),
            VRC700DHWSetpoint(coordinator),
            VRC700ManualCoolingDays(coordinator),
        ]
    )


class VRC700TempNumber(VRC700Entity, NumberEntity):
    """Base for the 0.5-degree temperature setters."""

    _attr_mode = NumberMode.BOX
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS


class VRC700HeatingDayTemp(VRC700TempNumber):
    """2c — heating Day temp -> PATCH comfort-room-temperature."""

    _attr_translation_key = "heating_day_temperature"
    _attr_native_min_value = 5
    _attr_native_max_value = 30
    _attr_icon = "mdi:thermometer-high"

    def __init__(self, coordinator: VRC700Coordinator) -> None:
        super().__init__(coordinator, "heating_day_temperature")

    @property
    def native_value(self) -> float | None:
        zone = self.coordinator.data.system.primary_zone
        return zone.heating_day_temp if zone else None

    async def async_set_native_value(self, value: float) -> None:
        coordinator = self.coordinator

        def mutate(data) -> None:
            if data.system.primary_zone:
                data.system.primary_zone.heating_day_temp = value

        await coordinator.async_write(
            coordinator.client.set_heating_day_temperature(coordinator.system_id, value),
            mutate,
        )


class VRC700HeatingSetbackTemp(VRC700TempNumber):
    """2b — heating Set-back temp."""

    _attr_translation_key = "heating_setback_temperature"
    _attr_native_min_value = 5
    _attr_native_max_value = 30
    _attr_icon = "mdi:thermometer-low"

    def __init__(self, coordinator: VRC700Coordinator) -> None:
        super().__init__(coordinator, "heating_setback_temperature")

    @property
    def native_value(self) -> float | None:
        zone = self.coordinator.data.system.primary_zone
        return zone.heating_setback_temp if zone else None

    async def async_set_native_value(self, value: float) -> None:
        coordinator = self.coordinator

        def mutate(data) -> None:
            if data.system.primary_zone:
                data.system.primary_zone.heating_setback_temp = value

        await coordinator.async_write(
            coordinator.client.set_heating_setback_temperature(
                coordinator.system_id, value
            ),
            mutate,
        )


class VRC700CoolingDayTemp(VRC700TempNumber):
    """3b — cooling Day temp."""

    _attr_translation_key = "cooling_day_temperature"
    _attr_native_min_value = 15
    _attr_native_max_value = 30
    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator: VRC700Coordinator) -> None:
        super().__init__(coordinator, "cooling_day_temperature")

    @property
    def native_value(self) -> float | None:
        zone = self.coordinator.data.system.primary_zone
        return zone.cooling_day_temp if zone else None

    async def async_set_native_value(self, value: float) -> None:
        coordinator = self.coordinator

        def mutate(data) -> None:
            if data.system.primary_zone:
                data.system.primary_zone.cooling_day_temp = value

        await coordinator.async_write(
            coordinator.client.set_cooling_day_temperature(coordinator.system_id, value),
            mutate,
        )


class VRC700DHWSetpoint(VRC700TempNumber):
    """6h-ii — hot water setpoint (0.5 steps via system-control tapping-setpoint)."""

    _attr_translation_key = "dhw_setpoint"
    _attr_icon = "mdi:water-thermometer"

    def __init__(self, coordinator: VRC700Coordinator) -> None:
        super().__init__(coordinator, "dhw_setpoint")

    @property
    def native_min_value(self) -> float:
        dhw = self.coordinator.data.system.primary_dhw
        return dhw.min_setpoint if dhw and dhw.min_setpoint else 35

    @property
    def native_max_value(self) -> float:
        dhw = self.coordinator.data.system.primary_dhw
        return dhw.max_setpoint if dhw and dhw.max_setpoint else 70

    @property
    def native_value(self) -> float | None:
        dhw = self.coordinator.data.system.primary_dhw
        return dhw.setpoint if dhw else None

    async def async_set_native_value(self, value: float) -> None:
        coordinator = self.coordinator
        dhw = coordinator.data.system.primary_dhw
        dhw_index = dhw.index if dhw else 255

        def mutate(data) -> None:
            if data.system.primary_dhw:
                data.system.primary_dhw.setpoint = value

        await coordinator.async_write(
            coordinator.client.set_dhw_setpoint(
                coordinator.system_id, value, dhw_index=dhw_index
            ),
            mutate,
        )


class VRC700ManualCoolingDays(VRC700Entity, RestoreNumber):
    """4 — days used when the Manual Cooling switch turns on (1-99).

    While manual cooling is running, shows the live remaining days from the
    controller and re-posts on change; while off, stores the value locally
    for the next activation (restored across restarts).
    """

    _attr_translation_key = "manual_cooling_days"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 99
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: VRC700Coordinator) -> None:
        super().__init__(coordinator, "manual_cooling_days")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (data := await self.async_get_last_number_data()) and data.native_value:
            self.coordinator.manual_cooling_days_setting = int(data.native_value)

    @property
    def native_value(self) -> float | None:
        system = self.coordinator.data.system
        if system.manual_cooling_active:
            return system.manual_cooling_days
        return self.coordinator.manual_cooling_days_setting

    async def async_set_native_value(self, value: float) -> None:
        days = int(value)
        coordinator = self.coordinator
        coordinator.manual_cooling_days_setting = days
        if coordinator.data.system.manual_cooling_active:
            def mutate(data) -> None:
                data.system.manual_cooling_days = days

            await coordinator.async_write(
                coordinator.client.start_manual_cooling(coordinator.system_id, days),
                mutate,
            )
        else:
            self.async_write_ha_state()
