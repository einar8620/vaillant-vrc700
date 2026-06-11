"""Constants for the Vaillant VRC 700 integration."""

from homeassistant.const import Platform

DOMAIN = "vaillant_vrc700"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SWITCH,
]

# Seconds to wait after a write (API returns 202 async) before re-polling
WRITE_REFRESH_DELAY = 8

CONF_BRAND = "brand"
CONF_COUNTRY = "country"
CONF_SYSTEM_ID = "system_id"
CONF_SYSTEM_NAME = "system_name"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_BOOST_DURATION = "boost_duration_minutes"
CONF_MANUAL_COOLING_DAYS = "manual_cooling_default_days"

DEFAULT_UPDATE_INTERVAL = 300  # seconds
MIN_UPDATE_INTERVAL = 60
DEFAULT_BOOST_DURATION = 30  # minutes (used from Phase C)
DEFAULT_MANUAL_COOLING_DAYS = 30  # used from Phase C

BRANDS = ["vaillant", "sdbg", "bulex", "glow-worm", "demirdokum"]

MANUFACTURER = "Vaillant"
