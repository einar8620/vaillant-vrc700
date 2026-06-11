"""Data update coordinator for the Vaillant VRC 700 integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, AuthenticationError, QuotaExceededError, VRC700Client, VRC700System
from .const import (
    CONF_MANUAL_COOLING_DAYS,
    CONF_SYSTEM_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_MANUAL_COOLING_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    WRITE_REFRESH_DELAY,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class VRC700Data:
    """Everything one update cycle fetches (3 API calls)."""

    system: VRC700System
    connected: bool = False
    trouble_codes: list[str] = field(default_factory=list)
    request_count: int = 0


class VRC700Coordinator(DataUpdateCoordinator[VRC700Data]):
    """Polls the myVAILLANT cloud for one VRC 700 system."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: VRC700Client
    ) -> None:
        self.client = client
        self.system_id: str = entry.data[CONF_SYSTEM_ID]
        # Days used when the manual-cooling switch is turned on (set via number entity)
        self.manual_cooling_days_setting: int = entry.options.get(
            CONF_MANUAL_COOLING_DAYS, DEFAULT_MANUAL_COOLING_DAYS
        )
        self._write_refresh_task: asyncio.Task | None = None
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {self.system_id[:8]}",
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )

    async def _async_update_data(self) -> VRC700Data:
        try:
            raw = await self.client.get_system_raw(self.system_id)
            system = VRC700System.from_api(self.system_id, raw)
            connected = await self.client.get_connection_status(self.system_id)
            dtcs = await self.client.get_trouble_codes(self.system_id)
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except QuotaExceededError as err:
            # Full adaptive backoff arrives in Phase D; for now surface clearly.
            raise UpdateFailed(f"API quota exceeded, backing off: {err}") from err
        except ApiError as err:
            raise UpdateFailed(f"API error: {err}") from err

        codes: list[str] = []
        for device in dtcs or []:
            for code in device.get("diagnosticTroubleCodes") or []:
                if isinstance(code, dict):
                    codes.append(str(code.get("code", code)))
                else:
                    codes.append(str(code))

        return VRC700Data(
            system=system,
            connected=connected,
            trouble_codes=codes,
            request_count=self.client.request_count,
        )

    # ------------------------------------------------------------ writes

    async def async_write(
        self,
        request: Awaitable,
        mutate: Callable[[VRC700Data], None] | None = None,
    ) -> None:
        """Run a write request, optimistically update state, refresh later.

        The cloud API returns 202 (applied asynchronously), so we mutate our
        local model immediately for a responsive UI, then re-poll after
        WRITE_REFRESH_DELAY seconds to confirm.
        """
        await request
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
