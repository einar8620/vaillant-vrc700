"""Parsed model of the VRC 700 system GET response.

The main read (GET vrc700/v1/systems/{id}) returns three blocks:
``configuration`` (user settings), ``state`` (live values) and
``properties`` (capabilities). Field paths below match a real captured
response (VRC 700 R6, system scheme 8).

Targets/modes are read from ``configuration.*``. Whether the
``state.zones[*].desiredRoomTemperatureSetpoint*`` fields are usable as
target temps is still to be verified during live testing (Phase B).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _get(d: Any, *path: Any, default: Any = None) -> Any:
    """Safe nested lookup across dicts and lists."""
    cur = d
    for p in path:
        try:
            cur = cur[p]
        except (KeyError, IndexError, TypeError):
            return default
    return cur


@dataclass
class Zone:
    index: int = 0
    name: str = ""
    is_active: bool = True
    # configuration
    heating_mode: str | None = None          # AUTO | DAY | SET_BACK | OFF
    heating_day_temp: float | None = None
    heating_setback_temp: float | None = None
    cooling_mode: str | None = None          # AUTO | DAY | OFF
    cooling_day_temp: float | None = None
    # state
    room_temperature: float | None = None
    humidity: float | None = None
    special_function: str | None = None


@dataclass
class Circuit:
    index: int = 0
    state: str | None = None                  # STANDBY | HEATING | COOLING
    flow_temperature: float | None = None
    heating_curve: float | None = None
    is_cooling_allowed: bool = False


@dataclass
class DomesticHotWater:
    index: int = 255
    mode: str | None = None                   # AUTO | DAY | OFF
    setpoint: float | None = None
    min_setpoint: float | None = None
    max_setpoint: float | None = None
    current_temperature: float | None = None
    special_function: str | None = None       # NONE | CYLINDER_BOOST | ...


@dataclass
class VRC700System:
    system_id: str = ""
    # state.system
    outdoor_temperature: float | None = None
    outdoor_temperature_avg24h: float | None = None
    water_pressure: float | None = None
    system_flow_temperature: float | None = None
    energy_manager_state: str | None = None   # STANDBY | HEATING | DHW
    system_off: bool | None = None
    # configuration.system
    manual_cooling_days: int = 0
    # properties.system
    controller_type: str | None = None
    controller_revision: str | None = None
    system_scheme: int | None = None
    # children
    zones: list[Zone] = field(default_factory=list)
    circuits: list[Circuit] = field(default_factory=list)
    dhw: list[DomesticHotWater] = field(default_factory=list)
    raw: dict = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------- derived

    @property
    def manual_cooling_active(self) -> bool:
        return self.manual_cooling_days > 0

    @property
    def primary_zone(self) -> Zone | None:
        return self.zones[0] if self.zones else None

    @property
    def primary_circuit(self) -> Circuit | None:
        return self.circuits[0] if self.circuits else None

    @property
    def primary_dhw(self) -> DomesticHotWater | None:
        return self.dhw[0] if self.dhw else None

    @property
    def system_status(self) -> str:
        """Heating | Cooling | Hot Water | Standby (requirement 6b)."""
        circuit = self.primary_circuit
        if self.energy_manager_state == "DHW":
            return "Hot Water"
        if circuit and circuit.state == "COOLING":
            return "Cooling"
        if circuit and circuit.state == "HEATING":
            return "Heating"
        if self.energy_manager_state == "HEATING":
            return "Heating"
        return "Standby"

    @property
    def dhw_status(self) -> str:
        """Boosting | Heating | Standby (requirement 6h-iii).

        'Heating' detection via energy_manager_state == DHW — to be
        confirmed live during Phase B."""
        dhw = self.primary_dhw
        if dhw and dhw.special_function == "CYLINDER_BOOST":
            return "Boosting"
        if self.energy_manager_state == "DHW":
            return "Heating"
        return "Standby"

    # ------------------------------------------------------------- parsing

    @classmethod
    def from_api(cls, system_id: str, data: dict) -> "VRC700System":
        conf = data.get("configuration", {})
        state = data.get("state", {})
        props = data.get("properties", {})

        zones: list[Zone] = []
        for zc in conf.get("zones", []):
            idx = zc.get("index", 0)
            zs = _first_by_index(state.get("zones", []), idx)
            zp = _first_by_index(props.get("zones", []), idx)
            zones.append(
                Zone(
                    index=idx,
                    name=str(_get(zc, "general", "name", default="")).strip(),
                    is_active=bool(_get(zp, "isActive", default=True)),
                    heating_mode=_get(zc, "heating", "operationModeHeating"),
                    heating_day_temp=_get(zc, "heating", "dayTemperatureHeating"),
                    heating_setback_temp=_get(zc, "heating", "setBackTemperature"),
                    cooling_mode=_get(zc, "cooling", "operationModeCooling"),
                    cooling_day_temp=_get(zc, "cooling", "setpointCooling"),
                    room_temperature=_get(zs, "currentRoomTemperature"),
                    humidity=_get(zs, "currentRoomHumidity"),
                    special_function=_get(zs, "currentSpecialFunction"),
                )
            )

        circuits: list[Circuit] = []
        for cc in conf.get("circuits", []):
            idx = cc.get("index", 0)
            cs = _first_by_index(state.get("circuits", []), idx)
            cp = _first_by_index(props.get("circuits", []), idx)
            circuits.append(
                Circuit(
                    index=idx,
                    state=_get(cs, "circuitState"),
                    flow_temperature=_get(cs, "currentCircuitFlowTemperature"),
                    heating_curve=_get(cc, "heatingCurve"),
                    is_cooling_allowed=bool(_get(cp, "isCoolingAllowed", default=False)),
                )
            )

        dhws: list[DomesticHotWater] = []
        for dc in conf.get("domesticHotWater", []):
            idx = dc.get("index", 255)
            ds = _first_by_index(state.get("domesticHotWater", []), idx)
            dp = _first_by_index(props.get("domesticHotWater", []), idx)
            dhws.append(
                DomesticHotWater(
                    index=idx,
                    mode=_get(dc, "operationModeDomesticHotWater"),
                    setpoint=_get(dc, "tappingSetpoint"),
                    min_setpoint=_get(dp, "minSetpoint"),
                    max_setpoint=_get(dp, "maxSetpoint"),
                    current_temperature=_get(ds, "currentDomesticHotWaterTemperature"),
                    special_function=_get(ds, "currentSpecialFunction"),
                )
            )

        return cls(
            system_id=system_id,
            outdoor_temperature=_get(state, "system", "outdoorTemperature"),
            outdoor_temperature_avg24h=_get(
                state, "system", "outdoorTemperatureAverage24h"
            ),
            water_pressure=_get(state, "system", "systemWaterPressure"),
            system_flow_temperature=_get(state, "system", "systemFlowTemperature"),
            energy_manager_state=_get(state, "system", "energyManagerState"),
            system_off=_get(state, "system", "systemOff"),
            manual_cooling_days=int(
                _get(conf, "system", "coolingForXDays", default=0) or 0
            ),
            controller_type=_get(props, "system", "controllerType"),
            controller_revision=_get(props, "system", "controllerRevision"),
            system_scheme=_get(props, "system", "systemScheme"),
            zones=zones,
            circuits=circuits,
            dhw=dhws,
            raw=data,
        )


def _first_by_index(items: list, index: int) -> dict:
    for item in items or []:
        if isinstance(item, dict) and item.get("index") == index:
            return item
    return {}
