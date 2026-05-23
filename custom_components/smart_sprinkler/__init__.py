"""The Smart Sprinkler integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_START_ZONE,
    SERVICE_STOP_ZONE,
    SERVICE_STOP_ALL,
    SERVICE_SET_RAIN_DELAY,
    ATTR_ZONE_ID,
    ATTR_DURATION,
    ATTR_RAIN_DELAY_DAYS,
)
from .coordinator import SprinklerCoordinator
from .frontend import SprinklerCardRegistration

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TIME,
]

START_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ZONE_ID): cv.string,
        vol.Optional(ATTR_DURATION, default=600): vol.All(int, vol.Range(min=1, max=7200)),
    }
)

STOP_ZONE_SCHEMA = vol.Schema({vol.Required(ATTR_ZONE_ID): cv.string})

RAIN_DELAY_SCHEMA = vol.Schema(
    {vol.Required(ATTR_RAIN_DELAY_DAYS): vol.All(int, vol.Range(min=1, max=14))}
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Sprinkler from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Merge options on top of data so options-flow changes are picked up
    config = {**entry.data, **entry.options}
    coordinator = SprinklerCoordinator(hass, entry.entry_id, config)
    await coordinator.async_restore_water_times()
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await coordinator.async_start_scheduler()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register frontend card
    cards = SprinklerCardRegistration(hass)
    await cards.async_register()

    # Register services (scoped to this entry)
    async def handle_start_zone(call: ServiceCall) -> None:
        coord: SprinklerCoordinator = hass.data[DOMAIN][entry.entry_id]
        zone_id = call.data[ATTR_ZONE_ID]
        duration = call.data.get(ATTR_DURATION, 600)

        skip, reason = await coord.async_check_weather()
        if skip:
            coord.weather_skip_reason = reason
            _LOGGER.info("Skipping zone %s due to weather: %s", zone_id, reason)
            return

        coord.weather_skip_reason = None
        await coord.async_start_zone(zone_id, duration)

    async def handle_stop_zone(call: ServiceCall) -> None:
        coord: SprinklerCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coord.async_stop_zone(call.data[ATTR_ZONE_ID])

    async def handle_stop_all(call: ServiceCall) -> None:
        coord: SprinklerCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coord.async_stop_all()

    async def handle_rain_delay(call: ServiceCall) -> None:
        coord: SprinklerCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coord.async_set_rain_delay(call.data[ATTR_RAIN_DELAY_DAYS])

    hass.services.async_register(DOMAIN, SERVICE_START_ZONE, handle_start_zone, START_ZONE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP_ZONE, handle_stop_zone, STOP_ZONE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP_ALL, handle_stop_all)
    hass.services.async_register(DOMAIN, SERVICE_SET_RAIN_DELAY, handle_rain_delay, RAIN_DELAY_SCHEMA)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: SprinklerCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_stop_scheduler()
        await coordinator.async_stop_all()

    cards = SprinklerCardRegistration(hass)
    await cards.async_unregister()

    for service in [SERVICE_START_ZONE, SERVICE_STOP_ZONE, SERVICE_STOP_ALL, SERVICE_SET_RAIN_DELAY]:
        hass.services.async_remove(DOMAIN, service)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
