"""Switch platform — zone on/off + controller enable/disable."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import SprinklerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SprinklerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SwitchEntity] = []

    # One switch per zone (manual activation)
    for zone_id, zone in coordinator.zones.items():
        entities.append(ZoneSwitch(coordinator, entry, zone_id))

    # Controller-level enable switch
    entities.append(ControllerEnabledSwitch(coordinator, entry))

    async_add_entities(entities)


class ZoneSwitch(CoordinatorEntity, SwitchEntity):
    """Toggle a zone on or off (using default duration)."""

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        zone = coordinator.zones[zone_id]
        self._attr_name = f"{zone.name}"
        self._attr_unique_id = f"{entry.entry_id}_zone_switch_{zone_id}"
        self._attr_icon = "mdi:sprinkler"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def is_on(self) -> bool:
        zone = self.coordinator.zones.get(self._zone_id)
        # True during startup delay (is_activating) AND while actually running
        return (zone.is_running or zone.is_activating) if zone else False

    async def async_turn_on(self, **kwargs: Any) -> None:
        zone = self.coordinator.zones.get(self._zone_id)
        duration = zone.default_duration if zone else 600

        skip, reason = await self.coordinator.async_check_weather()
        if skip:
            self.coordinator.weather_skip_reason = reason
            _LOGGER.info("Zone %s skipped due to weather: %s", self._zone_id, reason)
            return

        self.coordinator.weather_skip_reason = None
        await self.coordinator.async_start_zone(self._zone_id, duration)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_stop_zone(self._zone_id)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        zone = self.coordinator.zones.get(self._zone_id)
        if not zone:
            return {}
        return {
            "zone_id": self._zone_id,
            "remaining_seconds": zone.remaining_seconds,
            "last_run": zone.last_run.isoformat() if zone.last_run else None,
            "water_time_today_seconds": zone.water_time_today,
            "default_duration_seconds": zone.default_duration,
            "enabled": zone.is_enabled,
        }


class ControllerEnabledSwitch(CoordinatorEntity, SwitchEntity):
    """Master enable/disable for the whole controller (also pauses scheduler)."""

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = f"{entry.data.get('controller_name', NAME)} Enabled"
        self._attr_unique_id = f"{entry.entry_id}_controller_enabled"
        self._attr_icon = "mdi:sprinkler-variant"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator._controller_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator._controller_enabled = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator._controller_enabled = False
        await self.coordinator.async_stop_all()
        self.async_write_ha_state()
