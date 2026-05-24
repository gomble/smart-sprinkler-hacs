"""Select platform — schedule mode and weekday selection per zone."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME, SCHEDULE_MODES, WEEKDAYS
from .coordinator import SprinklerCoordinator

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SprinklerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for zone_id in coordinator.zones:
        entities.append(ZoneScheduleModeSelect(coordinator, entry, zone_id))
        entities.append(ZoneWeekdaysSelect(coordinator, entry, zone_id))

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

    @property
    def extra_state_attributes(self) -> dict:
        return {"zone_id": self._zone_id}

    async def async_select_option(self, option: str) -> None:
        zone = self.coordinator.zones.get(self._zone_id)
        if zone:
            zone.schedule["mode"] = option
            self.coordinator.update_next_runs()
            self.async_write_ha_state()
            await self.coordinator.async_save_schedule()
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class ZoneWeekdaysSelect(CoordinatorEntity, SelectEntity):
    """Select which weekdays this zone should run (for weekdays/custom mode).

    Each option encodes a combination like 'mon,wed,fri'. The user picks from
    common presets or sets individual days via the options list.
    """

    _attr_icon = "mdi:calendar-week"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        zone = coordinator.zones[zone_id]
        self._attr_name = f"{zone.name} Weekdays"
        self._attr_unique_id = f"{entry.entry_id}_zone_weekdays_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )
        self._attr_options = [
            "mon,tue,wed,thu,fri,sat,sun",
            "mon,wed,fri",
            "tue,thu,sat",
            "mon,tue,wed,thu,fri",
            "sat,sun",
            "mon",
            "tue",
            "wed",
            "thu",
            "fri",
            "sat",
            "sun",
        ]

    @property
    def current_option(self) -> str:
        zone = self.coordinator.zones.get(self._zone_id)
        if not zone:
            return "mon,wed,fri"
        days = zone.schedule.get("weekdays", [])
        return ",".join(days) if days else "mon,wed,fri"

    @property
    def extra_state_attributes(self) -> dict:
        return {"zone_id": self._zone_id}

    async def async_select_option(self, option: str) -> None:
        zone = self.coordinator.zones.get(self._zone_id)
        if zone:
            zone.schedule["weekdays"] = [d.strip() for d in option.split(",") if d.strip() in WEEKDAYS]
            self.coordinator.update_next_runs()
            self.async_write_ha_state()
            await self.coordinator.async_save_schedule()
            await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
