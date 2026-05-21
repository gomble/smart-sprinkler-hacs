"""Select platform — schedule mode per zone."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME, SCHEDULE_MODES
from .coordinator import SprinklerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SprinklerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for zone_id in coordinator.zones:
        entities.append(ZoneScheduleModeSelect(coordinator, entry, zone_id))

    async_add_entities(entities)


class ZoneScheduleModeSelect(CoordinatorEntity, SelectEntity):
    """Select the schedule mode for a zone."""

    _attr_options = SCHEDULE_MODES
    _attr_icon = "mdi:calendar-edit"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        zone = coordinator.zones[zone_id]
        self._attr_name = f"{zone.name} Schedule Mode"
        self._attr_unique_id = f"{entry.entry_id}_zone_schedule_mode_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def current_option(self) -> str:
        zone = self.coordinator.zones.get(self._zone_id)
        return zone.schedule.get("mode", "daily") if zone else "daily"

    async def async_select_option(self, option: str) -> None:
        zone = self.coordinator.zones.get(self._zone_id)
        if zone:
            zone.schedule["mode"] = option
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
