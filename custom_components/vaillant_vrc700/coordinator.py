"""Data update coordinator for the Vaillant VRC 700 integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ApiError, AuthenticationError, QuotaExceededError, VRC700Client, VRC700System
from .const import CONF_SYSTEM_ID, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN

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
