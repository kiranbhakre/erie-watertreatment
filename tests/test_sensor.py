from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from custom_components.erie_watertreatment.sensor import (
    ErieDaysSinceMaintenanceSensor,
    ErieDaysSinceRegenerationSensor,
    ErieDaysRemainingSensor,
    ErieRegenerationCountSensor,
    ErieRemainingLitresSensor,
    ErieRemainingPercentageSensor,
    ErieStatusSensor,
    ErieStatusTitleSensor,
    ErieVolumeIncreaseSensor,
    ErieWarning,
    ErieWaterConsumptionSensor,
    ErieWaterFlowRateSensor,
)


_BASE_DATA = {
    "last_regeneration": "2024-01-01T10:00:00",
    "nr_regenerations": "42",
    "last_maintenance": "2023-06-01",
    "total_volume": "5000",
    "warnings": [],
    "status_title": "In Service",
    "remaining_percentage": 98,
    "remaining_litres": "394",
    "days_remaining": 6,
    "holiday_mode": False,
}


def _coordinator(data=None):
    c = MagicMock()
    c.data = dict(_BASE_DATA) if data is None else data
    return c


# ---------------------------------------------------------------------------
# ErieWaterConsumptionSensor (Energy Dashboard)
# ---------------------------------------------------------------------------

def test_water_consumption_native_value():
    sensor = ErieWaterConsumptionSensor(_coordinator(), "device_123")
    assert sensor.native_value == 5000


def test_water_consumption_none_when_no_data():
    c = MagicMock()
    c.data = None
    assert ErieWaterConsumptionSensor(c, "device_123").native_value is None


def test_water_consumption_unique_id():
    sensor = ErieWaterConsumptionSensor(_coordinator(), "device_123")
    assert sensor.unique_id == "device_123_water_consumption"


def test_water_consumption_device_class():
    sensor = ErieWaterConsumptionSensor(_coordinator(), "device_123")
    assert sensor.device_class == "water"


def test_water_consumption_state_class():
    sensor = ErieWaterConsumptionSensor(_coordinator(), "device_123")
    assert sensor.state_class == "total_increasing"


def test_water_consumption_unit():
    sensor = ErieWaterConsumptionSensor(_coordinator(), "device_123")
    assert sensor.native_unit_of_measurement == "L"


# ---------------------------------------------------------------------------
# ErieWaterFlowRateSensor (normal sensor, L/h)
# ---------------------------------------------------------------------------

def _flow_rate_sensor(new_total, old_total_state):
    coordinator = _coordinator({"total_volume": str(new_total)})
    mock_hass = MagicMock()
    if old_total_state is not None:
        old = MagicMock()
        old.state = str(old_total_state)
        mock_hass.states.get.return_value = old
    else:
        mock_hass.states.get.return_value = None
    return ErieWaterFlowRateSensor(mock_hass, coordinator, "device_123")


def test_flow_rate_calculates_litres_per_hour():
    # delta=10 L over 120 s → 10 * (3600/120) = 300 L/h
    assert _flow_rate_sensor(5010, 5000).native_value == 300.0


def test_flow_rate_zero_on_first_run():
    assert _flow_rate_sensor(5000, None).native_value == 0


def test_flow_rate_zero_when_no_coordinator_data():
    c = MagicMock()
    c.data = None
    sensor = ErieWaterFlowRateSensor(MagicMock(), c, "device_123")
    assert sensor.native_value == 0


def test_flow_rate_never_negative():
    # old > new should not produce negative rate
    assert _flow_rate_sensor(5000, 5010).native_value == 0


def test_flow_rate_unique_id():
    assert _flow_rate_sensor(0, 0).unique_id == "device_123_water_flow_rate"


def test_flow_rate_unit():
    assert _flow_rate_sensor(0, 0).native_unit_of_measurement == "L/h"


def test_flow_rate_device_class():
    assert _flow_rate_sensor(0, 0).device_class == "volume_flow_rate"


def test_flow_rate_state_class():
    assert _flow_rate_sensor(0, 0).state_class == "measurement"


# ---------------------------------------------------------------------------
# ErieStatusSensor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("info_type,expected", [
    ("last_regeneration", "2024-01-01T10:00:00"),
    ("nr_regenerations", "42"),
    ("last_maintenance", "2023-06-01"),
    ("total_volume", "5000"),
])
def test_status_sensor_state(info_type, expected):
    assert ErieStatusSensor(_coordinator(), info_type, "").state == expected


def test_status_sensor_none_when_no_data():
    c = MagicMock()
    c.data = None
    assert ErieStatusSensor(c, "last_regeneration", "").state is None


def test_status_sensor_volume_unit():
    assert ErieStatusSensor(_coordinator(), "total_volume", "L").unit_of_measurement == "L"


def test_status_sensor_empty_unit():
    assert ErieStatusSensor(_coordinator(), "nr_regenerations", "").unit_of_measurement == ""


# ---------------------------------------------------------------------------
# ErieVolumeIncreaseSensor
# ---------------------------------------------------------------------------

def _flow_sensor(current_volume, old_state_value):
    coordinator = _coordinator({"total_volume": str(current_volume)})
    mock_hass = MagicMock()
    if old_state_value is not None:
        old = MagicMock()
        old.state = str(old_state_value)
        mock_hass.states.get.return_value = old
    else:
        mock_hass.states.get.return_value = None
    return ErieVolumeIncreaseSensor(mock_hass, coordinator, "total_volume", "flow", "L")


def test_flow_sensor_calculates_delta():
    assert _flow_sensor(6000, 5000).state == 1000


def test_flow_sensor_returns_zero_on_first_run():
    assert _flow_sensor(5000, None).state == 0


def test_flow_sensor_returns_zero_when_no_coordinator_data():
    c = MagicMock()
    c.data = None
    sensor = ErieVolumeIncreaseSensor(MagicMock(), c, "total_volume", "flow", "L")
    assert sensor.state == 0


def test_flow_sensor_state_class():
    # delta sensor fluctuates — measurement is the correct state class
    assert _flow_sensor(1000, 0).state_class == "measurement"


def test_flow_sensor_unit():
    assert _flow_sensor(1000, 0).unit_of_measurement == "L"


# ---------------------------------------------------------------------------
# ErieWarning
# ---------------------------------------------------------------------------

def test_warnings_sensor_formats_multiple_warnings():
    data = {**_BASE_DATA, "warnings": [{"description": "Low Salt"}, {"description": "Filter"}]}
    assert ErieWarning(_coordinator(data)).state == "⚠️ Low Salt\n⚠️ Filter\n"


def test_warnings_sensor_none_when_empty():
    data = {**_BASE_DATA, "warnings": []}
    assert ErieWarning(_coordinator(data)).state is None


def test_warnings_sensor_none_when_no_data():
    c = MagicMock()
    c.data = None
    assert ErieWarning(c).state is None


# ---------------------------------------------------------------------------
# ErieDaysSinceRegenerationSensor
# ---------------------------------------------------------------------------

def _regen_days_sensor(data=None):
    c = MagicMock()
    c.data = dict(_BASE_DATA) if data is None else data
    return ErieDaysSinceRegenerationSensor(c, "device_123")


def test_days_since_regen_calculates_correct_value():
    # _BASE_DATA has last_regeneration = "2024-01-01T10:00:00"
    # Pin now to 10 days later
    fixed_now = datetime(2024, 1, 11, 10, 0, 0, tzinfo=timezone.utc)
    with patch("custom_components.erie_watertreatment.sensor.datetime") as mock_dt:
        mock_dt.fromisoformat.side_effect = datetime.fromisoformat
        mock_dt.now.return_value = fixed_now
        assert _regen_days_sensor().native_value == 10


def test_days_since_regen_none_when_no_data():
    c = MagicMock()
    c.data = None
    assert ErieDaysSinceRegenerationSensor(c, "device_123").native_value is None


def test_days_since_regen_none_for_invalid_timestamp():
    data = {**_BASE_DATA, "last_regeneration": "not-a-date"}
    assert _regen_days_sensor(data).native_value is None


def test_days_since_regen_never_negative():
    data = {**_BASE_DATA, "last_regeneration": "2099-12-31T00:00:00"}
    val = _regen_days_sensor(data).native_value
    assert val is not None and val >= 0


def test_days_since_regen_unique_id():
    assert _regen_days_sensor().unique_id == "device_123_days_since_regeneration"


def test_days_since_regen_unit():
    assert _regen_days_sensor().native_unit_of_measurement == "d"


def test_days_since_regen_state_class():
    assert str(_regen_days_sensor().state_class) in ("measurement", "SensorStateClass.MEASUREMENT")


def test_days_since_regen_name():
    assert _regen_days_sensor().name == "Pentair Days Since Regeneration"


# ---------------------------------------------------------------------------
# ErieDaysSinceMaintenanceSensor
# ---------------------------------------------------------------------------

def _maint_days_sensor(data=None):
    c = MagicMock()
    c.data = dict(_BASE_DATA) if data is None else data
    return ErieDaysSinceMaintenanceSensor(c, "device_123")


def test_days_since_maint_calculates_correct_value():
    # _BASE_DATA has last_maintenance = "2023-06-01"
    fixed_today = date(2023, 7, 1)  # 30 days later
    with patch("custom_components.erie_watertreatment.sensor.date") as mock_date:
        mock_date.fromisoformat.side_effect = date.fromisoformat
        mock_date.today.return_value = fixed_today
        assert _maint_days_sensor().native_value == 30


def test_days_since_maint_none_when_no_data():
    c = MagicMock()
    c.data = None
    assert ErieDaysSinceMaintenanceSensor(c, "device_123").native_value is None


def test_days_since_maint_none_for_invalid_date():
    data = {**_BASE_DATA, "last_maintenance": "garbage"}
    assert _maint_days_sensor(data).native_value is None


def test_days_since_maint_never_negative():
    data = {**_BASE_DATA, "last_maintenance": "2099-01-01"}
    val = _maint_days_sensor(data).native_value
    assert val is not None and val >= 0


def test_days_since_maint_unique_id():
    assert _maint_days_sensor().unique_id == "device_123_days_since_maintenance"


def test_days_since_maint_unit():
    assert _maint_days_sensor().native_unit_of_measurement == "d"


def test_days_since_maint_state_class():
    assert str(_maint_days_sensor().state_class) in ("measurement", "SensorStateClass.MEASUREMENT")


def test_days_since_maint_name():
    assert _maint_days_sensor().name == "Pentair Days Since Maintenance"


# ---------------------------------------------------------------------------
# ErieRegenerationCountSensor
# ---------------------------------------------------------------------------

def _regen_count_sensor(data=None):
    c = MagicMock()
    c.data = dict(_BASE_DATA) if data is None else data
    return ErieRegenerationCountSensor(c, "device_123")


def test_regen_count_returns_int():
    assert _regen_count_sensor().native_value == 42


def test_regen_count_none_when_no_data():
    c = MagicMock()
    c.data = None
    assert ErieRegenerationCountSensor(c, "device_123").native_value is None


def test_regen_count_none_for_invalid_value():
    data = {**_BASE_DATA, "nr_regenerations": "N/A"}
    assert _regen_count_sensor(data).native_value is None


def test_regen_count_unique_id():
    assert _regen_count_sensor().unique_id == "device_123_regeneration_count"


def test_regen_count_state_class():
    assert str(_regen_count_sensor().state_class) in ("total_increasing", "SensorStateClass.TOTAL_INCREASING")


def test_regen_count_no_unit():
    assert _regen_count_sensor().native_unit_of_measurement is None


def test_regen_count_name():
    assert _regen_count_sensor().name == "Pentair Regeneration Count"


# ---------------------------------------------------------------------------
# ErieStatusTitleSensor
# ---------------------------------------------------------------------------

def _status_title_sensor(data=None):
    c = MagicMock()
    c.data = dict(_BASE_DATA) if data is None else data
    return ErieStatusTitleSensor(c, "device_123")


def test_status_title_returns_value():
    assert _status_title_sensor().native_value == "In Service"


def test_status_title_none_when_no_data():
    c = MagicMock()
    c.data = None
    assert ErieStatusTitleSensor(c, "device_123").native_value is None


def test_status_title_none_when_key_missing():
    data = {**_BASE_DATA, "status_title": None}
    assert _status_title_sensor(data).native_value is None


def test_status_title_unique_id():
    assert _status_title_sensor().unique_id == "device_123_status_title"


def test_status_title_name():
    assert _status_title_sensor().name == "Pentair Status"


# ---------------------------------------------------------------------------
# ErieRemainingPercentageSensor
# ---------------------------------------------------------------------------

def _pct_sensor(data=None):
    c = MagicMock()
    c.data = dict(_BASE_DATA) if data is None else data
    return ErieRemainingPercentageSensor(c, "device_123")


def test_remaining_pct_returns_value():
    assert _pct_sensor().native_value == 98


def test_remaining_pct_none_when_no_data():
    c = MagicMock()
    c.data = None
    assert ErieRemainingPercentageSensor(c, "device_123").native_value is None


def test_remaining_pct_none_when_key_missing():
    data = {**_BASE_DATA, "remaining_percentage": None}
    assert _pct_sensor(data).native_value is None


def test_remaining_pct_unique_id():
    assert _pct_sensor().unique_id == "device_123_remaining_percentage"


def test_remaining_pct_unit():
    assert _pct_sensor().native_unit_of_measurement == "%"


def test_remaining_pct_name():
    assert _pct_sensor().name == "Pentair Remaining Capacity %"


# ---------------------------------------------------------------------------
# ErieRemainingLitresSensor
# ---------------------------------------------------------------------------

def _litres_sensor(data=None):
    c = MagicMock()
    c.data = dict(_BASE_DATA) if data is None else data
    return ErieRemainingLitresSensor(c, "device_123")


def test_remaining_litres_returns_value():
    assert _litres_sensor().native_value == 394


def test_remaining_litres_none_when_no_data():
    c = MagicMock()
    c.data = None
    assert ErieRemainingLitresSensor(c, "device_123").native_value is None


def test_remaining_litres_none_when_key_missing():
    data = {**_BASE_DATA, "remaining_litres": None}
    assert _litres_sensor(data).native_value is None


def test_remaining_litres_unique_id():
    assert _litres_sensor().unique_id == "device_123_remaining_litres"


def test_remaining_litres_unit():
    assert _litres_sensor().native_unit_of_measurement == "L"


def test_remaining_litres_name():
    assert _litres_sensor().name == "Pentair Remaining Capacity L"


# ---------------------------------------------------------------------------
# ErieDaysRemainingSensor
# ---------------------------------------------------------------------------

def _days_remaining_sensor(data=None):
    c = MagicMock()
    c.data = dict(_BASE_DATA) if data is None else data
    return ErieDaysRemainingSensor(c, "device_123")


def test_days_remaining_returns_value():
    assert _days_remaining_sensor().native_value == 6


def test_days_remaining_none_when_no_data():
    c = MagicMock()
    c.data = None
    assert ErieDaysRemainingSensor(c, "device_123").native_value is None


def test_days_remaining_none_when_key_missing():
    data = {**_BASE_DATA, "days_remaining": None}
    assert _days_remaining_sensor(data).native_value is None


def test_days_remaining_unique_id():
    assert _days_remaining_sensor().unique_id == "device_123_days_remaining"


def test_days_remaining_unit():
    assert _days_remaining_sensor().native_unit_of_measurement == "d"


def test_days_remaining_name():
    assert _days_remaining_sensor().name == "Pentair Days Until Regeneration"
