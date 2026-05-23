"""Time platform — schedule start time per zone."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import SprinklerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SprinklerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for zone_id in coordinator.zones:
        entities.append(ZoneStartTimeEntity(coordinator, entry, zone_id))

    async_add_entities(entities)


class ZoneStartTimeEntity(CoordinatorEntity, TimeEntity):
    """The time of day this zone should start (used by the scheduler)."""

    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        zone = coordinator.zones[zone_id]
        self._attr_name = f"{zone.name} Start Time"
        self._attr_unique_id = f"{entry.entry_id}_zone_start_time_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> time | None:
        zone = self.coordinator.zones.get(self._zone_id)
        if not zone:
            return None
        h = zone.schedule.get("start_hour", 6)
        m = zone.schedule.get("start_minute", 0)
        return time(h, m)

    @property
    def extra_state_attributes(self) -> dict:
        return {"zone_id": self._zone_id}

    async def async_set_value(self, value: time) -> None:
        zone = self.coordinator.zones.get(self._zone_id)
        if zone:
            zone.schedule["start_hour"] = value.hour
            zone.schedule["start_minute"] = value.minute
            self.coordinator.update_next_runs()
            self.async_write_ha_state()
            await self.coordinator.async_save_schedule()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
