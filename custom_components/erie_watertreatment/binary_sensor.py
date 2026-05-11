"""Erie Water Treatment binary sensors.

All binary sensor classes read from the shared DataUpdateCoordinator.
They derive their on/off state from the 'warnings' list or specific
status flags in coordinator.data — no additional API calls are made.

Binary sensor overview:
    ErieLowSaltBinarySensor      – on when any warning mentions "Salt"
    ErieWarningBinarySensor      – parameterised; on when keyword found in warnings
    ErieAnyWarningBinarySensor   – on when the warnings list is non-empty
    ErieHolidayModeBinarySensor  – on when the softener is in bypass/holiday mode
"""
import logging

from homeassistant.helpers.entity import Entity

from . import get_coordinator
from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN
from .sensor import _device_info  # shared device registry helper

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entry-point: registers all binary sensor entities when the integration loads
# ---------------------------------------------------------------------------

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up all Erie binary sensor entities from a config entry.

    Called once by HA after async_setup_entry in __init__.py.
    Three ErieWarningBinarySensor instances are created with different
    keywords so each warning category gets its own binary sensor.
    """
    _LOGGER.debug(f"{DOMAIN}: binary_sensor: async_setup_entry: {entry}")
    coordinator = await get_coordinator(hass)
    device_id = entry.data[CONF_DEVICE_ID]
    device_name = entry.data.get(CONF_DEVICE_NAME, "Pentair Water Softener")

    async_add_entities([
        # ── Parameterised warning sensors (one per warning category) ──────
        # Each sensor triggers when the keyword appears in any warning description.
        # All use case-insensitive matching and carry a unique_id for HA tracking.
        ErieWarningBinarySensor(coordinator, device_id, "salt",    "salt_warning",    device_name),
        ErieWarningBinarySensor(coordinator, device_id, "filter",  "filter_warning",  device_name),
        ErieWarningBinarySensor(coordinator, device_id, "service", "service_warning", device_name),
        ErieWarningBinarySensor(coordinator, device_id, "error",   "error_warning",   device_name),

        # ── Catch-all: on when ANY warning is present ─────────────────────
        ErieAnyWarningBinarySensor(coordinator, device_id, device_name),

        # ── Device operating mode ─────────────────────────────────────────
        ErieHolidayModeBinarySensor(coordinator, device_id, device_name),
    ])


# ---------------------------------------------------------------------------
# Legacy binary sensor — kept for backward compatibility
# ---------------------------------------------------------------------------

class ErieLowSaltBinarySensor(Entity):
    """On (True) when any active warning description contains the word 'Salt'.

    This was the first binary sensor added to the integration.  It is kept
    as-is so existing automations don't break.  New installations should
    prefer ErieWarningBinarySensor(keyword='salt') which is case-insensitive.
    """

    def __init__(self, coordinator, device_id="", device_name=""):
        self.coordinator = coordinator
        self.info_type = "low_salt"
        self._device_id = device_id
        self._device_name = device_name

    @property
    def name(self):
        return "Pentair Low Salt"

    @property
    def device_class(self):
        # "problem" makes HA display the sensor as a red alert when on
        return "problem"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def state(self):
        """Return True when any active warning mentions salt, else False."""
        status = self.coordinator.data
        if status is None or not status["warnings"]:
            return False
        # Case-sensitive "Salt" match — preserved from the original implementation
        return any("Salt" in w["description"] for w in status["warnings"])


# ---------------------------------------------------------------------------
# Parameterised warning binary sensor — one instance per warning category
# ---------------------------------------------------------------------------

class ErieWarningBinarySensor(Entity):
    """On (True) when any warning description contains the given keyword.

    The keyword match is case-insensitive so 'FILTER CLOGGED' triggers
    a sensor created with keyword='filter'.  Multiple instances of this
    class are registered in async_setup_entry for different categories
    (filter, service, error).  Custom categories can be added in code.

    Args:
        coordinator:  DataUpdateCoordinator shared by all Erie entities.
        device_id:    Erie device ID — used to build the unique_id.
        keyword:      Substring to look for in warning descriptions (case-insensitive).
        sensor_name:  Suffix for the entity name and unique_id.
        device_name:  Human-readable device name shown in the HA device page.
    """

    def __init__(self, coordinator, device_id, keyword: str, sensor_name: str, device_name=""):
        self.coordinator = coordinator
        self._device_id = device_id
        self._keyword = keyword.lower()     # normalise once at construction time
        self._sensor_name = sensor_name
        self._device_name = device_name

    @property
    def unique_id(self):
        """Stable unique_id built from device_id + sensor_name."""
        return f"{self._device_id}_{self._sensor_name}"

    @property
    def name(self):
        # Friendly name: "Pentair Filter Warning", "Erie Service Warning", etc.
        return "Pentair " + self._sensor_name.replace("_", " ").title()

    @property
    def device_class(self):
        return "problem"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def state(self):
        """Return True when any warning description contains the keyword."""
        data = self.coordinator.data
        if data is None or not data["warnings"]:
            return False
        return any(
            self._keyword in w["description"].lower()
            for w in data["warnings"]
        )


# ---------------------------------------------------------------------------
# Catch-all binary sensor — on when any warning is active
# ---------------------------------------------------------------------------

class ErieAnyWarningBinarySensor(Entity):
    """On (True) when the warnings list is non-empty.

    Useful as a single trigger for automations that should fire regardless
    of the specific warning type (e.g. 'alert me when anything is wrong').
    """

    def __init__(self, coordinator, device_id, device_name=""):
        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

    @property
    def unique_id(self):
        return f"{self._device_id}_any_warning"

    @property
    def name(self):
        return "Pentair Any Warning"

    @property
    def device_class(self):
        return "problem"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def state(self):
        """Return True when the warnings list is non-empty, else False."""
        data = self.coordinator.data
        if data is None:
            return False
        return bool(data["warnings"])


# ---------------------------------------------------------------------------
# Holiday / bypass mode binary sensor
# ---------------------------------------------------------------------------

class ErieHolidayModeBinarySensor(Entity):
    """On (True) when the softener is in holiday (bypass) mode.

    In holiday mode the softener stops regenerating and bypasses water
    treatment — useful when you are away for an extended period.
    device_class='running' means HA shows it as active/inactive rather
    than as a problem/alert.
    """

    def __init__(self, coordinator, device_id, device_name=""):
        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

    @property
    def unique_id(self):
        return f"{self._device_id}_holiday_mode"

    @property
    def name(self):
        return "Pentair Holiday Mode"

    @property
    def device_class(self):
        # "running" displays as Active/Inactive in the HA UI
        return "running"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def state(self):
        """Return True when holiday mode is active, else False."""
        data = self.coordinator.data
        if data is None:
            return False
        return bool(data.get("holiday_mode", False))
