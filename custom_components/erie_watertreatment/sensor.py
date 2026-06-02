"""Erie Water Treatment sensors.

All sensor classes read from the shared DataUpdateCoordinator that polls
api.info() and api.dashboard() every 120 s.  No class makes its own API
calls — they only derive values from coordinator.data.

Coordinator data keys (populated in __init__.py::async_fetch_info):
    last_regeneration  – ISO datetime string of last regen cycle
    nr_regenerations   – string integer count of total regen cycles
    last_maintenance   – ISO date string of last service visit
    total_volume       – string integer, cumulative litres softened
    serial             – device serial number (may be None)
    software           – firmware version string (may be empty)
    warnings           – list of {"description": "..."} dicts
    status_title       – current status label from dashboard (e.g. "In Service")
    remaining_percentage – % of softening capacity left (int)
    remaining_litres   – litres of capacity remaining (string integer)
    days_remaining     – days until next auto-regeneration (int)
    holiday_mode       – bool, True when device is in bypass/holiday mode
"""
import logging
from datetime import date, datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfVolume, UnitOfVolumeFlowRate
from homeassistant.helpers.entity import Entity

from . import get_coordinator
from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    COORDINATOR_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _device_info(device_id, device_name, coordinator=None):
    """Build the HA device registry dict shared by every Erie entity.

    All entities that return the same ``identifiers`` value are grouped
    under a single device page in the HA UI.  The firmware version and
    serial number are injected from live coordinator data when available,
    so they appear in the Device Info card without requiring a separate
    config-flow field.

    Returns None (no device grouping) when device_id is falsy — this
    keeps legacy unit tests that construct sensors without a device_id
    from breaking.
    """
    if not device_id:
        return None
    info = {
        # Unique identifier for the device in HA's device registry
        "identifiers": {(DOMAIN, str(device_id))},
        "name": device_name or "Pentair Water Softener",
        "manufacturer": "Pentair",
        "model": "IQ26",
    }
    if coordinator and coordinator.data:
        # Populate firmware version from live coordinator data
        sw = str(coordinator.data.get("software", "")).strip()
        if sw:
            info["sw_version"] = sw
        # Populate serial number from live coordinator data
        serial = coordinator.data.get("serial")
        if serial:
            info["serial_number"] = str(serial)
    return info


# ---------------------------------------------------------------------------
# Entry-point: registers all sensor entities when the integration loads
# ---------------------------------------------------------------------------

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up all Erie sensor entities from a config entry.

    Called once by HA after async_setup_entry in __init__.py.
    Fetches the coordinator that was already created during setup so
    every sensor shares the same polling cycle.
    """
    _LOGGER.debug(f"{DOMAIN}: sensor: async_setup_entry: {entry}")

    coordinator = await get_coordinator(hass, entry)
    device_id = entry.data[CONF_DEVICE_ID]
    device_name = entry.data.get(CONF_DEVICE_NAME, "Pentair Water Softener")

    entities = [
        # ── Energy Dashboard (cumulative total) ──────────────────────────
        ErieWaterConsumptionSensor(coordinator, device_id, device_name),

        # ── Flow / rate sensors ──────────────────────────────────────────
        ErieWaterFlowRateSensor(hass, coordinator, device_id, device_name),
        ErieVolumeIncreaseSensor(hass, coordinator, "total_volume", "flow", "L", device_id, device_name),

        # ── Legacy raw-value sensors (plain Entity, kept for backward compat) ──
        ErieStatusSensor(coordinator, "last_regeneration", "", device_id, device_name),
        ErieStatusSensor(coordinator, "nr_regenerations",  "", device_id, device_name),
        ErieStatusSensor(coordinator, "last_maintenance",  "", device_id, device_name),
        ErieStatusSensor(coordinator, "total_volume",      "L", device_id, device_name),
        ErieWarning(coordinator, device_id, device_name),

        # ── Derived sensors (calculated locally, no extra API calls) ──────
        ErieDaysSinceRegenerationSensor(coordinator, device_id, device_name),
        ErieDaysSinceMaintenanceSensor(coordinator, device_id, device_name),
        ErieRegenerationCountSensor(coordinator, device_id, device_name),

        # ── Live status sensors (sourced from dashboard API status block) ─
        ErieStatusTitleSensor(coordinator, device_id, device_name),
        ErieRemainingPercentageSensor(coordinator, device_id, device_name),
        ErieRemainingLitresSensor(coordinator, device_id, device_name),
        ErieDaysRemainingSensor(coordinator, device_id, device_name),
    ]
    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Energy Dashboard sensor — cumulative total volume (device_class=water)
# ---------------------------------------------------------------------------

class ErieWaterConsumptionSensor(SensorEntity):
    """Cumulative water consumption — compatible with the HA Energy Dashboard.

    Uses state_class=TOTAL_INCREASING so HA can compute hourly/daily/monthly
    statistics from the ever-growing total_volume counter.  The value is the
    raw cumulative litre count reported by the softener since installation.
    """

    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS

    def __init__(self, coordinator, device_id, device_name=""):
        super().__init__()
        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

    @property
    def unique_id(self):
        return f"{self._device_id}_water_consumption"

    @property
    def name(self):
        return "Pentair Water Consumption"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def native_value(self):
        """Return cumulative litres as integer, or None when data unavailable."""
        if self.coordinator.data is None:
            return None
        return int(self.coordinator.data["total_volume"])

    async def async_update(self):
        await self.coordinator.async_request_refresh()


# ---------------------------------------------------------------------------
# Flow-rate sensor — instantaneous rate in L/h
# ---------------------------------------------------------------------------

class ErieWaterFlowRateSensor(SensorEntity):
    """Instantaneous water usage rate in L/h.

    Calculated by comparing the current total_volume reading with the
    previous state stored in hass.states.  The delta is scaled from the
    coordinator poll interval (120 s) to an hourly rate:
        rate = delta_litres × (3600 / poll_seconds)

    Returns 0 on the first poll (no previous state) and also clamps
    negative deltas (e.g. after a device reset) to 0 so the sensor
    never shows a negative flow.
    """

    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolumeFlowRate.LITERS_PER_HOUR
    # Snapshot of the coordinator polling period — used to scale L→L/h
    _POLL_SECONDS = int(COORDINATOR_UPDATE_INTERVAL.total_seconds())

    def __init__(self, hass, coordinator, device_id, device_name=""):
        super().__init__()
        self.hass = hass
        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

    @property
    def unique_id(self):
        return f"{self._device_id}_water_flow_rate"

    @property
    def name(self):
        return "Pentair Water Flow Rate"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def native_value(self):
        """Return instantaneous flow rate in L/h."""
        if self.coordinator.data is None:
            return 0
        new_total = int(self.coordinator.data["total_volume"])
        # Look up the previous total from the HA state machine
        old_state = self.hass.states.get(f"sensor.{DOMAIN}_total_volume")
        if old_state is None or old_state.state in ("unknown", "unavailable"):
            return 0  # First run — no previous reading to compare against
        try:
            old_total = int(old_state.state)
        except (ValueError, TypeError):
            return 0
        # Clamp to 0 to prevent negative rates after a counter reset
        delta = max(0, new_total - old_total)
        return round(delta * (3600 / self._POLL_SECONDS), 1)

    async def async_update(self):
        await self.coordinator.async_request_refresh()


# ---------------------------------------------------------------------------
# Legacy sensors — plain Entity subclasses (kept for backward compatibility)
# These were the original sensors before SensorEntity was adopted.
# They still appear on the device page via device_info but do NOT benefit
# from HA's long-term statistics (no state_class / native_value pattern).
# ---------------------------------------------------------------------------

class ErieVolumeIncreaseSensor(Entity):
    """Delta volume sensor — litres consumed since the previous poll.

    Unlike ErieWaterFlowRateSensor (which normalises to L/h), this sensor
    returns the raw litre delta observed during the last polling window.
    Kept for dashboards and automations that were built against it.
    Grouped under Diagnostics on the device page (raw/legacy value).
    """

    # Mark as diagnostic so it appears in the Diagnostics section on the device page
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass, coordinator, info_type, sensor_name, unit, device_id="", device_name=""):
        self.hass = hass
        self.coordinator = coordinator
        self.info_type = info_type      # coordinator.data key to watch
        self.sensor_name = sensor_name  # suffix used in the entity_id
        self.unit = unit
        self._device_id = device_id
        self._device_name = device_name

    @property
    def name(self):
        # Friendly name: "Pentair Flow" (title-cased from sensor_name)
        return "Pentair " + self.sensor_name.replace("_", " ").title()

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def state(self):
        """Return litres consumed since the last coordinator refresh."""
        sensor_entity_id = f"sensor.{DOMAIN}_{self.info_type}"
        old_state = self.hass.states.get(sensor_entity_id)
        _LOGGER.debug(f"{sensor_entity_id}: data={self.coordinator.data} old={old_state}")
        if self.coordinator.data and self.info_type in self.coordinator.data and old_state:
            old_value = self._to_int(old_state.state)
            new_value = self._to_int(self.coordinator.data[self.info_type])
            return new_value - old_value
        return 0

    @property
    def unit_of_measurement(self):
        return self.unit

    @property
    def state_class(self):
        # Delta value — fluctuates up and down each poll, so MEASUREMENT is correct
        return "measurement"

    def _to_int(self, value):
        """Parse a value that may be '1234 L' or '1234' to int."""
        if value is not None:
            return int(str(value).split()[0])
        return 0

    async def async_update(self):
        await self.coordinator.async_request_refresh()


class ErieWarning(Entity):
    """Active warnings displayed as a multi-line formatted string.

    Returns None (sensor becomes unavailable/empty) when there are no
    active warnings so it doesn't clutter dashboards.  Each warning is
    prefixed with a ⚠️ emoji and terminated with a newline.
    """

    def __init__(self, coordinator, device_id="", device_name=""):
        self.coordinator = coordinator
        self.info_type = "warnings"     # coordinator.data key
        self._device_id = device_id
        self._device_name = device_name

    @property
    def name(self):
        return "Pentair Warnings"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def state(self):
        """Return formatted warning string, or None when no warnings are active."""
        _LOGGER.debug(f"{DOMAIN}: sensor: state: {self.coordinator.data}")
        if self.coordinator.data is None:
            return None
        warning_string = "".join(
            f"⚠️ {w['description']}\n"
            for w in self.coordinator.data[self.info_type]
        )
        # Return None (not empty string) so templates can use `if states(...)` cleanly
        return warning_string or None


class ErieStatusSensor(Entity):
    """Generic read-only sensor that exposes a single coordinator.data value.

    Used for fields like last_regeneration, nr_regenerations, last_maintenance,
    and total_volume where no transformation is needed.  The info_type parameter
    selects the key from coordinator.data and also forms the entity name/ID.
    Grouped under Diagnostics on the device page (raw/legacy values).
    """

    # Mark as diagnostic so it appears in the Diagnostics section on the device page
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, info_type, unit, device_id="", device_name=""):
        self.coordinator = coordinator
        self.info_type = info_type  # key in coordinator.data
        self.unit = unit            # "" for dimensionless values
        self._device_id = device_id
        self._device_name = device_name

    @property
    def name(self):
        # Friendly name: "Pentair Last Regeneration", "Erie Total Volume", etc.
        return "Pentair " + self.info_type.replace("_", " ").title()

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def state(self):
        """Return the raw coordinator value, or None when data is unavailable."""
        _LOGGER.debug(f"{DOMAIN}: sensor: state: {self.coordinator.data}")
        if self.coordinator.data is not None:
            return self.coordinator.data[self.info_type]
        return None

    @property
    def unit_of_measurement(self):
        return self.unit


# ---------------------------------------------------------------------------
# Derived sensors — calculated locally from coordinator data
# No additional API calls are made; values are derived from fields already
# fetched by async_fetch_info() in __init__.py.
# ---------------------------------------------------------------------------

class ErieDaysSinceRegenerationSensor(SensorEntity):
    """Number of whole days elapsed since the last regeneration cycle.

    Parses last_regeneration as an ISO datetime, assumes UTC when no
    timezone info is present, then computes (now − regen_dt).days.
    Clamped to ≥0 so a future-dated timestamp (clock skew) still shows 0.
    """

    _attr_native_unit_of_measurement = "d"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_id, device_name=""):
        super().__init__()
        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

    @property
    def unique_id(self):
        return f"{self._device_id}_days_since_regeneration"

    @property
    def name(self):
        return "Pentair Days Since Regeneration"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def native_value(self):
        """Return whole days since last regeneration, or None on missing/invalid data."""
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get("last_regeneration")
        if not raw:
            return None
        try:
            regen_dt = datetime.fromisoformat(raw)
            # Treat naive datetimes from the API as UTC
            if regen_dt.tzinfo is None:
                regen_dt = regen_dt.replace(tzinfo=timezone.utc)
            delta = datetime.now(tz=timezone.utc) - regen_dt
            return max(0, delta.days)
        except (ValueError, TypeError):
            return None

    async def async_update(self):
        await self.coordinator.async_request_refresh()


class ErieDaysSinceMaintenanceSensor(SensorEntity):
    """Number of whole days elapsed since the last service maintenance visit.

    Parses last_maintenance as an ISO date string (YYYY-MM-DD) and computes
    (today − maintenance_date).days.  Clamped to ≥0.
    """

    _attr_native_unit_of_measurement = "d"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_id, device_name=""):
        super().__init__()
        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

    @property
    def unique_id(self):
        return f"{self._device_id}_days_since_maintenance"

    @property
    def name(self):
        return "Pentair Days Since Maintenance"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def native_value(self):
        """Return whole days since last maintenance visit, or None on invalid data."""
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get("last_maintenance")
        if not raw:
            return None
        try:
            # Strip any time component (e.g. "2023-06-01T00:00:00" → "2023-06-01")
            # so date.fromisoformat() works correctly on both date and datetime strings.
            date_str = str(raw).split("T")[0]
            maintenance_date = date.fromisoformat(date_str)
            delta = date.today() - maintenance_date
            return max(0, delta.days)
        except (ValueError, TypeError):
            return None

    async def async_update(self):
        await self.coordinator.async_request_refresh()


class ErieRegenerationCountSensor(SensorEntity):
    """Total number of regeneration cycles performed since installation.

    Uses state_class=TOTAL_INCREASING so HA can track cumulative stats.
    The raw API value is a string integer (e.g. "42"); it is cast to int.
    Returns None on parse failure so HA marks the sensor as unavailable
    rather than displaying a misleading 0.
    """

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = None  # dimensionless count

    def __init__(self, coordinator, device_id, device_name=""):
        super().__init__()
        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

    @property
    def unique_id(self):
        return f"{self._device_id}_regeneration_count"

    @property
    def name(self):
        return "Pentair Regeneration Count"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def native_value(self):
        """Return total regeneration count as int, or None on invalid data."""
        if self.coordinator.data is None:
            return None
        try:
            return int(self.coordinator.data["nr_regenerations"])
        except (ValueError, TypeError):
            return None

    async def async_update(self):
        await self.coordinator.async_request_refresh()


# ---------------------------------------------------------------------------
# Live status sensors — sourced from the dashboard API status block
# These fields are fetched from api.dashboard() inside async_fetch_info().
# ---------------------------------------------------------------------------

class ErieStatusTitleSensor(SensorEntity):
    """Current operational status title as reported by the device dashboard.

    Examples: 'In Service', 'Regenerating', 'Bypassed'.
    Returns None (unavailable) when the status block is absent or data
    hasn't loaded yet.
    """

    def __init__(self, coordinator, device_id, device_name=""):
        super().__init__()
        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

    @property
    def unique_id(self):
        return f"{self._device_id}_status_title"

    @property
    def name(self):
        return "Pentair Status"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def native_value(self):
        """Return status title string, or None when unavailable."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("status_title")

    async def async_update(self):
        await self.coordinator.async_request_refresh()


class ErieRemainingPercentageSensor(SensorEntity):
    """Remaining softening capacity as a percentage (0–100).

    Sourced from the dashboard status block's 'percentage' field.
    Cast to int; returns None on missing or non-numeric values.
    """

    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_id, device_name=""):
        super().__init__()
        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

    @property
    def unique_id(self):
        return f"{self._device_id}_remaining_percentage"

    @property
    def name(self):
        return "Pentair Remaining Capacity %"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def native_value(self):
        """Return remaining capacity percentage as int, or None when unavailable."""
        if self.coordinator.data is None:
            return None
        val = self.coordinator.data.get("remaining_percentage")
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    async def async_update(self):
        await self.coordinator.async_request_refresh()


class ErieRemainingLitresSensor(SensorEntity):
    """Remaining softening capacity in litres.

    Sourced from the 'extra' field in the dashboard status block after
    stripping the unit suffix (e.g. '394 L' → 394).
    Returns None on missing or non-numeric values.
    """

    _attr_native_unit_of_measurement = "L"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_id, device_name=""):
        super().__init__()
        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

    @property
    def unique_id(self):
        return f"{self._device_id}_remaining_litres"

    @property
    def name(self):
        return "Pentair Remaining Capacity L"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def native_value(self):
        """Return remaining capacity in litres as int, or None when unavailable."""
        if self.coordinator.data is None:
            return None
        val = self.coordinator.data.get("remaining_litres")
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    async def async_update(self):
        await self.coordinator.async_request_refresh()


class ErieDaysRemainingSensor(SensorEntity):
    """Days remaining until the next automatic regeneration cycle.

    This value comes directly from the device firmware via the dashboard
    API — it is NOT calculated locally from last_regeneration.  That means
    it accounts for the softener's own demand-based scheduling logic.
    Returns None on missing or non-numeric values.
    """

    _attr_native_unit_of_measurement = "d"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_id, device_name=""):
        super().__init__()
        self.coordinator = coordinator
        self._device_id = device_id
        self._device_name = device_name

    @property
    def unique_id(self):
        return f"{self._device_id}_days_remaining"

    @property
    def name(self):
        return "Pentair Days Until Regeneration"

    @property
    def device_info(self):
        """Link this entity to the Erie device page in the HA UI."""
        return _device_info(self._device_id, self._device_name, self.coordinator)

    @property
    def native_value(self):
        """Return days until next regeneration as int, or None when unavailable."""
        if self.coordinator.data is None:
            return None
        val = self.coordinator.data.get("days_remaining")
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    async def async_update(self):
        await self.coordinator.async_request_refresh()
