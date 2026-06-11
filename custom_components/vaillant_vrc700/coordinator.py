"""Data update coordinator for the Vaillant VRC 700 integration.

Quota strategy (the myVAILLANT API allows roughly ~100 calls/hour):
- main system read every cycle (1 call); connection-status + trouble-codes
  only every AUX_FETCH_EVERY_CYCLES cycles (2 extra calls)
- on "Quota Exceeded" the replenish time is parsed from the error and
  polling pauses until then (+margin); entities keep their last values
  (stale) instead of going unavailable
- writes during a quota pause fail fast with a clear error
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ApiError, AuthenticationError, QuotaExceededError, VRC700Client, VRC700System
from .const import (
    AUX_FETCH_EVERY_CYCLES,
    CONF_MANUAL_COOLING_DAYS,
    CONF_SYSTEM_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_MANUAL_COOLING_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    QUOTA_PAUSE_FALLBACK,
    QUOTA_PAUSE_MARGIN,
    WRITE_REFRESH_DELAY,
)

_LOGGER = logging.getLogger(__name__)

_QUOTA_TIME_RE = re.compile(r"replenished in (\d{2}):(\d{2}):(\d{2})")


def extract_quota_pause_seconds(message: str) -> int:
    """Parse 'Quota will be replenished in HH:MM:SS' into seconds."""
    if match := _QUOTA_TIME_RE.search(message):
        h, m, s = (int(g) for g in match.groups())
        return h * 3600 + m * 60 + s
    return QUOTA_PAUSE_FALLBACK


@dataclass
class VRC700Data:
    """Everything exposed to entities."""

    system: VRC700System
    connected: bool = False
    trouble_codes: list[str] = field(default_factory=list)
    request_count: int = 0
    quota_paused_until: datetime | None = None


class VRC700Coordinator(DataUpdateCoordinator[VRC700Data]):
    """Polls the myVAILLANT cloud for one VRC 700 system."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: VRC700Client
    ) -> None:
        self.client = client
        self.system_id: str = entry.data[CONF_SYSTEM_ID]
        self.manual_cooling_days_setting: int = entry.options.get(
            CONF_MANUAL_COOLING_DAYS, DEFAULT_MANUAL_COOLING_DAYS
        )
        self.quota_paused_until: datetime | None = None
        self._cycle = 0
        self._force_aux = False
        self._last_connected = False
        self._last_codes: list[str] = []
        self._write_refresh_task: asyncio.Task | None = None
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {self.system_id[:8]}",
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )

    # ----------------------------------------------------------------- quota

    @property
    def quota_paused(self) -> bool:
        return (
            self.quota_paused_until is not None
            and dt_util.utcnow() < self.quota_paused_until
        )

    def _enter_quota_pause(self, err: Exception) -> None:
        seconds = extract_quota_pause_seconds(str(err)) + QUOTA_PAUSE_MARGIN
        self.quota_paused_until = dt_util.utcnow() + timedelta(seconds=seconds)
        _LOGGER.warning(
            "API quota exhausted — pausing polls until %s (%s s). "
            "Entities keep their last values meanwhile",
            self.quota_paused_until.isoformat(timespec="seconds"),
            seconds,
        )

    # ----------------------------------------------------------------- reads

    def force_aux_fetch(self) -> None:
        """Make the next cycle also fetch connection-status + trouble codes."""
        self._force_aux = True

    async def _async_update_data(self) -> VRC700Data:
        if self.quota_paused:
            if self.data:
                # Keep serving the last known values while paused.
                self.data.quota_paused_until = self.quota_paused_until
                return self.data
            raise UpdateFailed(
                f"API quota exhausted, paused until {self.quota_paused_until}"
            )

        try:
            raw = await self.client.get_system_raw(self.system_id)
            system = VRC700System.from_api(self.system_id, raw)

            self._cycle += 1
            if self._force_aux or self._cycle % AUX_FETCH_EVERY_CYCLES == 1:
                self._force_aux = False
                self._last_connected = await self.client.get_connection_status(
                    self.system_id
                )
                dtcs = await self.client.get_trouble_codes(self.system_id)
                codes: list[str] = []
                for device in dtcs or []:
                    for code in device.get("diagnosticTroubleCodes") or []:
                        codes.append(
                            str(code.get("code", code))
                            if isinstance(code, dict)
                            else str(code)
                        )
                self._last_codes = codes
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except QuotaExceededError as err:
            self._enter_quota_pause(err)
            if self.data:
                self.data.quota_paused_until = self.quota_paused_until
                return self.data
            raise UpdateFailed(f"API quota exceeded: {err}") from err
        except ApiError as err:
            raise UpdateFailed(f"API error: {err}") from err

        self.quota_paused_until = None
        return VRC700Data(
            system=system,
            connected=self._last_connected,
            trouble_codes=self._last_codes,
            request_count=self.client.request_count,
            quota_paused_until=None,
        )

    # ------------------------------------------------------------ writes

    async def async_write(
        self,
        request: Awaitable,
        mutate: Callable[[VRC700Data], None] | None = None,
    ) -> None:
        """Run a write request, optimistically update state, refresh later."""
        if self.quota_paused:
            request.close()  # don't leave the coroutine un-awaited
            raise HomeAssistantError(
                "myVAILLANT API quota is exhausted — writes are paused until "
                f"{self.quota_paused_until:%H:%M:%S}"
            )
        try:
            await request
        except QuotaExceededError as err:
            self._enter_quota_pause(err)
            raise HomeAssistantError(
                "myVAILLANT API quota is exhausted — the change was NOT applied. "
                f"Paused until {self.quota_paused_until:%H:%M:%S}"
            ) from err
        if mutate and self.data:
            mutate(self.data)
            self.async_update_listeners()
        if self._write_refresh_task and not self._write_refresh_task.done():
            self._write_refresh_task.cancel()
        self._write_refresh_task = self.hass.async_create_task(
            self._refresh_after_write()
        )

    async def _refresh_after_write(self) -> None:
        await asyncio.sleep(WRITE_REFRESH_DELAY)
        await self.async_request_refresh()
