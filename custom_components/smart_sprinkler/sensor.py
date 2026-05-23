"""Sensor platform — water time, next run, controller status, moisture estimate."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME, STATUS_IDLE
from .coordinator import SprinklerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SprinklerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    for zone_id in coordinator.zones:
        entities.append(ZoneWaterTimeSensor(coordinator, entry, zone_id))
        entities.append(ZoneRemainingTimeSensor(coordinator, entry, zone_id))
        entities.append(ZoneNextRunSensor(coordinator, entry, zone_id))

    entities.append(ControllerStatusSensor(coordinator, entry))
    entities.append(TotalWaterTimeSensor(coordinator, entry))

    async_add_entities(entities)


class ZoneWaterTimeSensor(CoordinatorEntity, SensorEntity):
    """Total seconds the zone has watered today."""

    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        zone = coordinator.zones[zone_id]
        self._attr_name = f"{zone.name} Water Time Today"
        self._attr_unique_id = f"{entry.entry_id}_zone_water_time_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> int:
        zone = self.coordinator.zones.get(self._zone_id)
        return zone.water_time_today if zone else 0

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class ZoneRemainingTimeSensor(CoordinatorEntity, SensorEntity):
    """Remaining seconds for the currently active run."""

    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        zone = coordinator.zones[zone_id]
        self._attr_name = f"{zone.name} Remaining Time"
        self._attr_unique_id = f"{entry.entry_id}_zone_remaining_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> int:
        zone = self.coordinator.zones.get(self._zone_id)
        return zone.remaining_seconds if zone else 0

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class ZoneNextRunSensor(CoordinatorEntity, SensorEntity):
    """Timestamp of the next scheduled run."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        zone = coordinator.zones[zone_id]
        self._attr_name = f"{zone.name} Next Run"
        self._attr_unique_id = f"{entry.entry_id}_zone_next_run_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self):
        zone = self.coordinator.zones.get(self._zone_id)
        return zone.next_run if zone else None

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class ControllerStatusSensor(CoordinatorEntity, SensorEntity):
    """Overall controller status string."""

    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"{entry.data.get('controller_name', NAME)} Status"
        self._attr_unique_id = f"{entry.entry_id}_controller_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> str:
        return self.coordinator.status

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "active_zones": self.coordinator.active_zone_ids,
            "rain_delay_until": (
                self.coordinator.rain_delay_until.isoformat()
                if self.coordinator.rain_delay_until
                else None
            ),
            "weather_skip_reason": self.coordinator.weather_skip_reason,
            "total_water_time_today": self.coordinator.total_water_time_today,
            "valve_delay_remaining": self.coordinator.valve_delay_remaining,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class TotalWaterTimeSensor(CoordinatorEntity, SensorEntity):
    """Total watering seconds across all zones today."""

    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:water-percent"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"{entry.data.get('controller_name', NAME)} Total Water Time Today"
        self._attr_unique_id = f"{entry.entry_id}_total_water_time"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> int:
        return self.coordinator.total_water_time_today

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
