from unittest.mock import MagicMock

import pytest

from custom_components.erie_watertreatment import create_coordinator
from custom_components.erie_watertreatment.const import COORDINATOR, DOMAIN


async def test_coordinator_parses_info_and_dashboard(hass, mock_erie_api, mock_config_entry):
    mock_config_entry.add_to_hass(hass)
    coordinator = await create_coordinator(hass, mock_config_entry, mock_erie_api)

    assert coordinator.data["last_regeneration"] == "2024-01-01"
    assert coordinator.data["nr_regenerations"] == "42"
    assert coordinator.data["last_maintenance"] == "2023-06-01"
    assert coordinator.data["total_volume"] == "5000"
    assert coordinator.data["warnings"] == [{"description": "Low Salt Level"}]


async def test_total_volume_strips_unit(hass, mock_config_entry):
    mock_config_entry.add_to_hass(hass)
    api = MagicMock()
    api.info.return_value.content = {
        "last_regeneration": "2024-01-01",
        "nr_regenerations": "10",
        "last_maintenance": "2023-01-01",
        "total_volume": "1234 L",
    }
    api.dashboard.return_value.content = {"warnings": []}

    coordinator = await create_coordinator(hass, mock_config_entry, api)

    assert coordinator.data["total_volume"] == "1234"


async def test_coordinator_on_api_error_marks_update_failed(hass, mock_config_entry):
    mock_config_entry.add_to_hass(hass)
    api = MagicMock()
    api.info.side_effect = Exception("connection refused")

    coordinator = await create_coordinator(hass, mock_config_entry, api)

    assert coordinator.last_update_success is False
    assert coordinator.data is None


async def test_coordinator_stored_per_entry(hass, mock_erie_api, mock_config_entry):
    """Each config entry gets its own coordinator slot in hass.data."""
    mock_config_entry.add_to_hass(hass)
    coordinator = await create_coordinator(hass, mock_config_entry, mock_erie_api)

    assert DOMAIN in hass.data
    assert mock_config_entry.entry_id in hass.data[DOMAIN]
    assert hass.data[DOMAIN][mock_config_entry.entry_id][COORDINATOR] is coordinator
