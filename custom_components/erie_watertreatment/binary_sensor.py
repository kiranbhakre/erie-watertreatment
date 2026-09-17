"""Erie Water Treatment binary sensors.

All binary sensor classes read from the shared DataUpdateCoordinator.
They derive their on/off state from the 'warnings' list or specific
status flags in coordinator.data — no additional API calls are made.

Binary sensor overview:
    ErieWarningBinarySensor      – parameterised; on when any alias found in warnings
    ErieAnyWarningBinarySensor   – on when the warnings list is non-empty
    ErieHolidayModeBinarySensor  – on when the softener is in bypass/holiday mode
"""
import logging
from typing import Iterable, Union

from homeassistant.helpers.entity import Entity

from . import get_coordinator
from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN
from .sensor import _device_info  # shared device registry helper

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Warning keyword aliases per category
# ---------------------------------------------------------------------------
# The Pentair/Erie cloud returns warning descriptions in the account's
# configured language, so English-only substring matching misses users with
# a non-English locale (see issue #4). Each tuple lists lowercase substrings
# that indicate the given warning category across supported locales.
# Add new locales here — no other code changes needed.

SALT_KEYWORDS = ("salt", "sale", "zout", "sel", "salz", "sól", "sal")
FILTER_KEYWORDS = ("filter", "filtro", "filtre", "filtr")
SERVICE_KEYWORDS = (
    "service", "servizio", "assistenza", "manutenzione",
    "onderhoud", "entretien", "wartung", "mantenimiento",
    "servicio", "serwis", "konserwacja",
)
ERROR_KEYWORDS = ("error", "errore", "erreur", "fout", "fehler", "błąd")


# ---------------------------------------------------------------------------
# Entry-point: registers all binary sensor entities when the integration loads
# ---------------------------------------------------------------------------

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up all Erie binary sensor entities from a config entry.

    Called once by HA after async_setup_entry in __init__.py.
    Four ErieWarningBinarySensor instances are created, one per warning
    category, each with a multi-language alias list.
    """
    _LOGGER.debug(f"{DOMAIN}: binary_sensor: async_setup_entry: {entry}")
    coordinator = await get_coordinator(hass, entry)
    device_id = entry.data[CONF_DEVICE_ID]
    device_name = entry.data.get(CONF_DEVICE_NAME, "Pentair Water Softener")

    async_add_entities([
        # ── Parameterised warning sensors (one per warning category) ──────
        # Each sensor triggers when any of the alias substrings appears in
        # a warning description. Matching is case-insensitive.
        ErieWarningBinarySensor(coordinator, device_id, SALT_KEYWORDS,    "salt_warning",    device_name),
        ErieWarningBinarySensor(coordinator, device_id, FILTER_KEYWORDS,  "filter_warning",  device_name),
        ErieWarningBinarySensor(coordinator, device_id, SERVICE_KEYWORDS, "service_warning", device_name),
        ErieWarningBinarySensor(coordinator, device_id, ERROR_KEYWORDS,   "error_warning",   device_name),

        # ── Catch-all: on when ANY warning is present ─────────────────────
        ErieAnyWarningBinarySensor(coordinator, device_id, device_name),

        # ── Device operating mode ─────────────────────────────────────────
        ErieHolidayModeBinarySensor(coordinator, device_id, device_name),
    ])


# ---------------------------------------------------------------------------
# Parameterised warning binary sensor — one instance per warning category
# ---------------------------------------------------------------------------

class ErieWarningBinarySensor(Entity):
    """On (True) when any warning description contains one of the aliases.

    Args:
        coordinator:  DataUpdateCoordinator shared by all Erie entities.
        device_id:    Erie device ID — used to build the unique_id.
        keywords:     Substring alias(es) to look for in warning descriptions.
                      Accepts a single string or an iterable of strings for
                      multi-language support. Matching is case-insensitive.
        sensor_name:  Suffix for the entity name and unique_id.
        device_name:  Human-readable device name shown in the HA device page.
    """

    def __init__(
        self,
        coordinator,
        device_id,
        keywords: Union[str, Iterable[str]],
        sensor_name: str,
        device_name: str = "",
    ):
        self.coordinator = coordinator
        self._device_id = device_id
        if isinstance(keywords, str):
            keywords = (keywords,)
        self._keywords = tuple(k.lower() for k in keywords)
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
        """Return True when any warning description contains any alias."""
        data = self.coordinator.data
        if data is None or not data["warnings"]:
            return False
        for w in data["warnings"]:
            desc = str(w.get("description", "")).lower()
            if any(kw in desc for kw in self._keywords):
                return True
        return False


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
