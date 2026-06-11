"""Thin HTTP client for VRC 700 systems on the myVAILLANT cloud.

Every endpoint here was verified against mitmproxy captures of the real
myVAILLANT app on a live VRC 700 R6 system (2026-06). Three API bases are
used — this split is essential, the official app does exactly this:

- vrc700/v1         most reads/writes specific to VRC 700 systems
- system-control/v1 operation modes, DHW tapping setpoint, heat-demand limit
- end-user-app-api/v1  discovery, connection status, trouble codes

Write endpoints return HTTP 202 (accepted, applied asynchronously) — allow a
few seconds before re-reading state.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .auth import VaillantAuth

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.vaillant-group.com/service-connected-control"

# Shared by all myVAILLANT clients (from the official app).
SUBSCRIPTION_KEY = "1e0a2f3511fb4c5bbb1c7f9fedd20b1c"

HEATING_MODES = ("AUTO", "DAY", "SET_BACK", "OFF")
COOLING_MODES = ("AUTO", "DAY", "OFF")
DHW_MODES = ("AUTO", "DAY", "OFF")

MANUAL_COOLING_MAX_DAYS = 99  # app-side limit, not enforced by the API


class ApiError(Exception):
    """Generic myVAILLANT API error."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class QuotaExceededError(ApiError):
    """API quota exhausted — back off before retrying."""


def _validate(value: str, allowed: tuple[str, ...], what: str) -> str:
    value = value.upper()
    if value not in allowed:
        raise ValueError(f"Invalid {what} '{value}', expected one of {allowed}")
    return value


class VRC700Client:
    """Async client bound to one myVAILLANT account."""

    def __init__(self, session: aiohttp.ClientSession, auth: VaillantAuth) -> None:
        self._session = session
        self._auth = auth
        self.request_count = 0

    # ------------------------------------------------------------------ core

    async def _request(
        self, method: str, url: str, json: Any | None = None
    ) -> Any:
        token = await self._auth.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "ocp-apim-subscription-key": SUBSCRIPTION_KEY,
            "x-app-identifier": "VAILLANT",
            "x-idm-identifier": "KEYCLOAK",
            "Accept": "application/json",
            "User-Agent": "okhttp/4.9.2",
        }
        self.request_count += 1
        async with self._session.request(
            method, url, json=json, headers=headers
        ) as resp:
            body = await resp.text()
            if resp.status in (200, 201, 202, 204):
                if not body or not body.strip():
                    return None
                if "json" in resp.headers.get("Content-Type", ""):
                    return await resp.json(content_type=None)
                return body
            if "quota" in body.lower():
                raise QuotaExceededError(
                    f"Quota exceeded: {body[:300]}", resp.status
                )
            raise ApiError(
                f"{method} {url} -> HTTP {resp.status}: {body[:300]}",
                resp.status,
            )

    # URL builders -----------------------------------------------------------

    @staticmethod
    def _vrc700(system_id: str) -> str:
        return f"{API_BASE}/vrc700/v1/systems/{system_id}"

    @staticmethod
    def _control(system_id: str) -> str:
        return f"{API_BASE}/system-control/v1/systems/{system_id}"

    @staticmethod
    def _app(path: str) -> str:
        return f"{API_BASE}/end-user-app-api/v1{path}"

    # ----------------------------------------------------------------- reads

    async def get_homes(self) -> list[dict]:
        """List systems on the account (discovery, used at setup)."""
        return await self._request("GET", self._app("/homes")) or []

    async def get_control_identifier(self, system_id: str) -> str:
        data = await self._request(
            "GET", self._app(f"/systems/{system_id}/meta-info/control-identifier")
        )
        return (data or {}).get("controlIdentifier", "unknown")

    async def get_system_raw(self, system_id: str) -> dict:
        """Main system read: configuration + state + properties in one call."""
        return await self._request("GET", self._vrc700(system_id))

    async def get_connection_status(self, system_id: str) -> bool:
        data = await self._request(
            "GET", self._app(f"/systems/{system_id}/meta-info/connection-status")
        )
        return bool((data or {}).get("connected", False))

    async def get_trouble_codes(self, system_id: str) -> list[dict]:
        """Diagnostic trouble codes (errors) per device."""
        return (
            await self._request(
                "GET", self._app(f"/systems/{system_id}/diagnostic-trouble-codes")
            )
            or []
        )

    # -------------------------------------------------------- heating writes

    async def set_heating_operation_mode(
        self, system_id: str, mode: str, zone: int = 0
    ) -> None:
        mode = _validate(mode, HEATING_MODES, "heating mode")
        await self._request(
            "PATCH",
            f"{self._control(system_id)}/zones/{zone}/heating-operation-mode",
            json={"operationMode": mode},
        )

    async def set_heating_day_temperature(
        self, system_id: str, temperature: float, zone: int = 0
    ) -> None:
        await self._request(
            "PATCH",
            f"{self._vrc700(system_id)}/zone/{zone}/heating/comfort-room-temperature",
            json={"comfortRoomTemperature": round(temperature * 2) / 2},
        )

    async def set_heating_setback_temperature(
        self, system_id: str, temperature: float, zone: int = 0
    ) -> None:
        await self._request(
            "PATCH",
            f"{self._vrc700(system_id)}/zone/{zone}/heating/set-back-temperature",
            json={"setBackTemperature": round(temperature * 2) / 2},
        )

    # -------------------------------------------------------- cooling writes

    async def set_cooling_operation_mode(
        self, system_id: str, mode: str, zone: int = 0
    ) -> None:
        mode = _validate(mode, COOLING_MODES, "cooling mode")
        await self._request(
            "PATCH",
            f"{self._control(system_id)}/zones/{zone}/cooling-operation-mode",
            json={"operationMode": mode},
        )

    async def set_cooling_day_temperature(
        self, system_id: str, temperature: float, zone: int = 0
    ) -> None:
        await self._request(
            "PATCH",
            f"{self._vrc700(system_id)}/zone/{zone}/cooling/setpoint",
            json={"setpoint": round(temperature * 2) / 2},
        )

    async def start_manual_cooling(self, system_id: str, days: int) -> None:
        """Enable manual cooling for N days (app allows 1-99)."""
        if not 1 <= days <= MANUAL_COOLING_MAX_DAYS:
            raise ValueError(
                f"days must be 1-{MANUAL_COOLING_MAX_DAYS}, got {days}"
            )
        await self._request(
            "POST",
            f"{self._vrc700(system_id)}/cooling-for-days",
            json={"value": days},
        )

    async def stop_manual_cooling(self, system_id: str) -> None:
        await self._request(
            "DELETE", f"{self._vrc700(system_id)}/cooling-for-days"
        )

    # ------------------------------------------------------------ DHW writes

    async def set_dhw_operation_mode(
        self, system_id: str, mode: str, dhw_index: int = 255
    ) -> None:
        mode = _validate(mode, DHW_MODES, "DHW mode")
        await self._request(
            "PATCH",
            f"{self._vrc700(system_id)}/domestic-hot-water/{dhw_index}/operation-mode",
            json={"operationMode": mode},
        )

    async def set_dhw_setpoint(
        self, system_id: str, temperature: float, dhw_index: int = 255
    ) -> None:
        """Set hot water target temp (0.5 deg steps supported on this endpoint)."""
        await self._request(
            "PATCH",
            f"{self._control(system_id)}/domestic-hot-water/{dhw_index}/tapping-setpoint",
            json={"setpoint": round(temperature * 2) / 2},
        )

    async def start_dhw_boost(self, system_id: str, dhw_index: int = 255) -> None:
        """Cylinder boost. No duration parameter — runs until setpoint is
        reached, or until stop_dhw_boost() is called (integration adds the
        30-minute timer)."""
        await self._request(
            "POST",
            f"{self._vrc700(system_id)}/domestic-hot-water/{dhw_index}/boost",
            json={},
        )

    async def stop_dhw_boost(self, system_id: str, dhw_index: int = 255) -> None:
        await self._request(
            "DELETE",
            f"{self._vrc700(system_id)}/domestic-hot-water/{dhw_index}/boost",
        )
