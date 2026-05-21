"""Binary sensors — zone active, rain delay active, freeze protection."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
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
        entities.append(ZoneActiveBinarySensor(coordinator, entry, zone_id))

    entities.append(RainDelayBinarySensor(coordinator, entry))
    entities.append(AnyZoneActiveBinarySensor(coordinator, entry))

    async_add_entities(entities)


class ZoneActiveBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """True when the zone is currently watering."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        zone = coordinator.zones[zone_id]
        self._attr_name = f"{zone.name} Active"
        self._attr_unique_id = f"{entry.entry_id}_zone_active_{zone_id}"
        self._attr_icon = "mdi:water"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def is_on(self) -> bool:
        zone = self.coordinator.zones.get(self._zone_id)
        return (zone.is_running or zone.is_activating) if zone else False

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        zone = self.coordinator.zones.get(self._zone_id)
        if not zone:
            return {}
        return {
            "remaining_seconds": zone.remaining_seconds,
            "started_at": zone.started_at.isoformat() if zone.started_at else None,
        }


class AnyZoneActiveBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """True when any zone is running (useful for pump automations)."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"{entry.data.get('controller_name', NAME)} Running"
        self._attr_unique_id = f"{entry.entry_id}_any_zone_active"
        self._attr_icon = "mdi:sprinkler"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def is_on(self) -> bool:
        return any(z.is_running for z in self.coordinator.zones.values())

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "active_zone": self.coordinator.active_zone_id,
            "status": self.coordinator.status,
        }


class RainDelayBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """True when a rain delay is active."""

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"{entry.data.get('controller_name', NAME)} Rain Delay"
        self._attr_unique_id = f"{entry.entry_id}_rain_delay"
        self._attr_icon = "mdi:weather-rainy"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.rain_delay_until is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        rd = self.coordinator.rain_delay_until
        return {"rain_delay_until": rd.isoformat() if rd else None}
