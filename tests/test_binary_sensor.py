from unittest.mock import MagicMock

from custom_components.erie_watertreatment.binary_sensor import (
    ErieAnyWarningBinarySensor,
    ErieHolidayModeBinarySensor,
    ErieLowSaltBinarySensor,
    ErieWarningBinarySensor,
)


def _sensor(warnings):
    c = MagicMock()
    c.data = {"warnings": warnings}
    return ErieLowSaltBinarySensor(c)


def test_low_salt_true_when_salt_in_description():
    assert _sensor([{"description": "Low Salt Level"}]).state is True


def test_low_salt_false_when_no_salt_in_description():
    assert _sensor([{"description": "Filter Replacement Needed"}]).state is False


def test_low_salt_false_when_no_warnings():
    assert _sensor([]).state is False


def test_low_salt_false_when_data_is_none():
    c = MagicMock()
    c.data = None
    assert ErieLowSaltBinarySensor(c).state is False


def test_device_class_is_problem():
    assert _sensor([]).device_class == "problem"


# ---------------------------------------------------------------------------
# ErieWarningBinarySensor — salt
# ---------------------------------------------------------------------------

def test_salt_true_when_salt_in_description():
    assert _warning_sensor("salt", "salt_warning",
                           [{"description": "Low Salt Level"}]).state is True


def test_salt_false_when_different_warning():
    assert _warning_sensor("salt", "salt_warning",
                           [{"description": "Filter Replacement Needed"}]).state is False


def test_salt_false_when_no_warnings():
    assert _warning_sensor("salt", "salt_warning", []).state is False


def test_salt_case_insensitive():
    assert _warning_sensor("salt", "salt_warning",
                           [{"description": "SALT LEVEL LOW"}]).state is True


def test_salt_unique_id():
    assert _warning_sensor("salt", "salt_warning", []).unique_id == "device_123_salt_warning"


def test_salt_name():
    assert _warning_sensor("salt", "salt_warning", []).name == "Pentair Salt Warning"


# ---------------------------------------------------------------------------
# ErieWarningBinarySensor — filter
# ---------------------------------------------------------------------------

def _warning_sensor(keyword, sensor_name, warnings):
    c = MagicMock()
    c.data = {"warnings": warnings}
    return ErieWarningBinarySensor(c, "device_123", keyword, sensor_name)


def test_filter_true_when_filter_in_description():
    assert _warning_sensor("filter", "filter_warning",
                           [{"description": "Filter Replacement Needed"}]).state is True


def test_filter_false_when_different_warning():
    assert _warning_sensor("filter", "filter_warning",
                           [{"description": "Low Salt Level"}]).state is False


def test_filter_false_when_no_warnings():
    assert _warning_sensor("filter", "filter_warning", []).state is False


def test_filter_false_when_data_is_none():
    c = MagicMock()
    c.data = None
    assert ErieWarningBinarySensor(c, "device_123", "filter", "filter_warning").state is False


def test_filter_case_insensitive():
    assert _warning_sensor("filter", "filter_warning",
                           [{"description": "FILTER CLOGGED"}]).state is True


def test_filter_unique_id():
    assert _warning_sensor("filter", "filter_warning", []).unique_id == "device_123_filter_warning"


# ---------------------------------------------------------------------------
# ErieWarningBinarySensor — service
# ---------------------------------------------------------------------------

def test_service_true_when_service_in_description():
    assert _warning_sensor("service", "service_warning",
                           [{"description": "Service Required"}]).state is True


def test_service_false_when_no_service_warning():
    assert _warning_sensor("service", "service_warning",
                           [{"description": "Low Salt Level"}]).state is False


def test_service_unique_id():
    assert _warning_sensor("service", "service_warning",
                           []).unique_id == "device_123_service_warning"


# ---------------------------------------------------------------------------
# ErieWarningBinarySensor — error
# ---------------------------------------------------------------------------

def test_error_true_when_error_in_description():
    assert _warning_sensor("error", "error_warning",
                           [{"description": "System Error Detected"}]).state is True


def test_error_false_when_no_error_warning():
    assert _warning_sensor("error", "error_warning",
                           [{"description": "Low Salt Level"}]).state is False


def test_error_unique_id():
    assert _warning_sensor("error", "error_warning",
                           []).unique_id == "device_123_error_warning"


# ---------------------------------------------------------------------------
# ErieAnyWarningBinarySensor
# ---------------------------------------------------------------------------

def _any_sensor(warnings, data_none=False):
    c = MagicMock()
    c.data = None if data_none else {"warnings": warnings}
    return ErieAnyWarningBinarySensor(c, "device_123")


def test_any_warning_true_when_one_warning():
    assert _any_sensor([{"description": "Low Salt Level"}]).state is True


def test_any_warning_true_when_multiple_warnings():
    assert _any_sensor([
        {"description": "Low Salt Level"},
        {"description": "Filter Replacement Needed"},
    ]).state is True


def test_any_warning_false_when_empty():
    assert _any_sensor([]).state is False


def test_any_warning_false_when_data_is_none():
    assert _any_sensor([], data_none=True).state is False


def test_any_warning_unique_id():
    assert _any_sensor([]).unique_id == "device_123_any_warning"


def test_any_warning_device_class_is_problem():
    assert _any_sensor([]).device_class == "problem"


# ---------------------------------------------------------------------------
# ErieHolidayModeBinarySensor
# ---------------------------------------------------------------------------

def _holiday_sensor(holiday_mode, data_none=False):
    c = MagicMock()
    c.data = None if data_none else {"holiday_mode": holiday_mode, "warnings": []}
    return ErieHolidayModeBinarySensor(c, "device_123")


def test_holiday_mode_true_when_on():
    assert _holiday_sensor(True).state is True


def test_holiday_mode_false_when_off():
    assert _holiday_sensor(False).state is False


def test_holiday_mode_false_when_data_is_none():
    assert _holiday_sensor(False, data_none=True).state is False


def test_holiday_mode_unique_id():
    assert _holiday_sensor(False).unique_id == "device_123_holiday_mode"


def test_holiday_mode_device_class():
    assert _holiday_sensor(False).device_class == "running"
