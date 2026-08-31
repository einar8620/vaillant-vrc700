"""Config flow for the Vaillant VRC 700 integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import AuthenticationError, AuthServerError, VaillantAuth, VRC700Client
from .const import (
    BRANDS,
    CONF_BOOST_DURATION,
    CONF_BRAND,
    CONF_COUNTRY,
    CONF_MANUAL_COOLING_DAYS,
    CONF_SYSTEM_ID,
    CONF_SYSTEM_NAME,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BOOST_DURATION,
    DEFAULT_MANUAL_COOLING_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

CONF_IMPORT_MYPYLLANT = "import_from_mypyllant"


class VRC700ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup: credentials -> discover systems -> pick VRC700 system."""

    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._systems: list[dict] = []

    def _mypyllant_credentials(self) -> dict[str, Any] | None:
        """Borrow credentials from an existing myVAILLANT (mypyllant) entry."""
        for entry in self.hass.config_entries.async_entries("mypyllant"):
            data = entry.data
            if data.get("username") and data.get("password"):
                return {
                    CONF_USERNAME: data["username"],
                    CONF_PASSWORD: data["password"],
                    CONF_BRAND: data.get("brand", "vaillant"),
                    CONF_COUNTRY: data.get("country", ""),
                }
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        mypyllant_creds = self._mypyllant_credentials()

        if user_input is not None:
            if user_input.get(CONF_IMPORT_MYPYLLANT) and mypyllant_creds:
                creds = mypyllant_creds
            else:
                creds = {
                    CONF_USERNAME: (user_input.get(CONF_USERNAME) or "").strip(),
                    CONF_PASSWORD: user_input.get(CONF_PASSWORD) or "",
                    CONF_BRAND: user_input.get(CONF_BRAND, "vaillant"),
                    CONF_COUNTRY: (user_input.get(CONF_COUNTRY) or "").strip().lower(),
                }
            if not creds[CONF_USERNAME] or not creds[CONF_PASSWORD]:
                errors["base"] = "missing_credentials"
            else:
                try:
                    self._systems = await self._discover_vrc700_systems(creds)
                except AuthServerError:
                    errors["base"] = "cannot_connect"
                except AuthenticationError:
                    errors["base"] = "invalid_auth"
                except Exception:  # noqa: BLE001 - surface as connection problem
                    _LOGGER.exception("Unexpected error during discovery")
                    errors["base"] = "cannot_connect"
                else:
                    if not self._systems:
                        errors["base"] = "no_vrc700_system"
                    else:
                        self._credentials = creds
                        return await self.async_step_select_system()

        schema: dict[Any, Any] = {}
        if mypyllant_creds:
            schema[vol.Optional(CONF_IMPORT_MYPYLLANT, default=True)] = bool
        schema.update(
            {
                vol.Optional(CONF_USERNAME, default=""): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
                vol.Optional(CONF_BRAND, default="vaillant"): vol.In(BRANDS),
                vol.Optional(CONF_COUNTRY, default="spain"): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(schema), errors=errors
        )

    async def _discover_vrc700_systems(self, creds: dict[str, Any]) -> list[dict]:
        session = async_create_clientsession(self.hass)
        try:
            auth = VaillantAuth(
                session,
                creds[CONF_USERNAME],
                creds[CONF_PASSWORD],
                brand=creds[CONF_BRAND],
                country=creds[CONF_COUNTRY] or None,
            )
            await auth.login()
            client = VRC700Client(session, auth)
            homes = await client.get_homes()
            systems = []
            for home in homes:
                system_id = home.get("systemId")
                if not system_id:
                    continue
                ci = await client.get_control_identifier(system_id)
                if ci == "vrc700":
                    systems.append(
                        {"system_id": system_id, "name": home.get("homeName") or system_id}
                    )
            return systems
        finally:
            await session.close()

    async def async_step_select_system(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None and len(self._systems) == 1:
            user_input = {CONF_SYSTEM_ID: self._systems[0]["system_id"]}

        if user_input is not None:
            system_id = user_input[CONF_SYSTEM_ID]
            name = next(
                (s["name"] for s in self._systems if s["system_id"] == system_id),
                system_id,
            )
            await self.async_set_unique_id(system_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"VRC700 ({name})",
                data={**self._credentials, CONF_SYSTEM_ID: system_id, CONF_SYSTEM_NAME: name},
            )

        return self.async_show_form(
            step_id="select_system",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SYSTEM_ID): vol.In(
                        {s["system_id"]: s["name"] for s in self._systems}
                    )
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> "VRC700OptionsFlow":
        return VRC700OptionsFlow()


class VRC700OptionsFlow(OptionsFlow):
    """Options: polling interval and Phase C defaults."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_UPDATE_INTERVAL, max=3600)),
                    vol.Optional(
                        CONF_BOOST_DURATION,
                        default=options.get(CONF_BOOST_DURATION, DEFAULT_BOOST_DURATION),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=240)),
                    vol.Optional(
                        CONF_MANUAL_COOLING_DAYS,
                        default=options.get(
                            CONF_MANUAL_COOLING_DAYS, DEFAULT_MANUAL_COOLING_DAYS
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=99)),
                }
            ),
        )
