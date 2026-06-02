"""Erie IQ26 Water Treatment integration"""

import asyncio
import logging

import async_timeout
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import exceptions
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from erie_connect.client import ErieConnect

from .const import (
    API,
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_ID,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_EMAIL,
    CONF_EXPIRY,
    CONF_PASSWORD,
    CONF_UID,
    COORDINATOR,
    COORDINATOR_UPDATE_INTERVAL,
    DOMAIN,
)

PLATFORMS = ["sensor", "binary_sensor"]

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema(vol.All(cv.ensure_list, [vol.Schema({vol.Required(CONF_ACCESS_TOKEN): cv.string})]))},
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    _LOGGER.debug(f"{DOMAIN}: async_setup")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.debug(f"{DOMAIN}: async_setup_entry: entry {entry}")

    api = ErieConnect(
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        ErieConnect.Auth(
            entry.data[CONF_ACCESS_TOKEN],
            entry.data[CONF_CLIENT_ID],
            entry.data[CONF_UID],
            entry.data[CONF_EXPIRY],
        ),
        ErieConnect.Device(entry.data[CONF_DEVICE_ID], entry.data[CONF_DEVICE_NAME]),
    )
    # The erie-connect library hardcodes _debugmode=True and uses print() for
    # all debug output — it cannot be controlled via HA's logger config.
    # Disable it here to prevent STDOUT spam in HA logs.
    api._debugmode = False

    await create_coordinator(hass, entry, api)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok


async def get_coordinator(hass, entry):
    """Return the DataUpdateCoordinator for the given config entry."""
    return hass.data[DOMAIN][entry.entry_id][COORDINATOR]


async def create_coordinator(hass, entry, api):
    """Create a per-entry data update coordinator."""
    hass.data.setdefault(DOMAIN, {})

    async def async_fetch_info():
        try:
            async with async_timeout.timeout(120):
                response = await hass.async_add_executor_job(api.info)
                response_dashboard = await hass.async_add_executor_job(api.dashboard)
            status = response_dashboard.content.get("status", {})
            return {
                "last_regeneration": response.content["last_regeneration"],
                "nr_regenerations": response.content["nr_regenerations"],
                "last_maintenance": response.content["last_maintenance"],
                "total_volume": response.content["total_volume"].split()[0],
                "serial": response.content.get("serial"),
                "software": str(response.content.get("software", "")).strip(),
                "warnings": response_dashboard.content["warnings"],
                # Status fields from dashboard
                "status_title": status.get("title"),
                "remaining_percentage": status.get("percentage"),
                "remaining_litres": str(status.get("extra", "")).split()[0] if status.get("extra") else None,
                "days_remaining": status.get("days_remaining"),
                "holiday_mode": response_dashboard.content.get("holiday_mode", False),
            }
        except Exception:
            raise SensorUpdateFailed

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=DOMAIN,
        update_method=async_fetch_info,
        update_interval=COORDINATOR_UPDATE_INTERVAL,
    )

    hass.data[DOMAIN][entry.entry_id] = {COORDINATOR: coordinator, API: api}
    await coordinator.async_refresh()
    return coordinator


class SensorUpdateFailed(exceptions.HomeAssistantError):
    """Error to indicate we get invalid data from the device."""
