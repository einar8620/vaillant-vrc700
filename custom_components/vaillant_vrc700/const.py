"""Constants for the Vaillant VRC 700 integration."""

from homeassistant.const import Platform

DOMAIN = "vaillant_vrc700"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.BUTTON,
]

# Seconds to wait after a write (API returns 202 async) before re-polling
WRITE_REFRESH_DELAY = 8

# Re-apply optimistic write state on refreshes until the API confirms it,
# for at most this long (202-async writes can lag well past the refresh delay)
OPTIMISTIC_HOLD_SECONDS = 90

# Connection-status + trouble-codes are fetched only every Nth poll cycle
# (the quota is roughly ~100 calls/hour; this keeps most cycles at 1 call)
AUX_FETCH_EVERY_CYCLES = 6

# Safety margin added to the server-reported quota replenish time
QUOTA_PAUSE_MARGIN = 60  # seconds
QUOTA_PAUSE_FALLBACK = 1800  # if the replenish time can't be parsed

# Minimum seconds between presses of the refresh button
REFRESH_BUTTON_COOLDOWN = 60

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
