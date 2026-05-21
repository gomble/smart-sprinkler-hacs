"""Number platform — duration and thresholds per zone."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime, UnitOfTemperature, UnitOfSpeed
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    NAME,
    CONF_RAIN_THRESHOLD,
    CONF_WIND_THRESHOLD,
    CONF_TEMP_MIN,
    CONF_VALVE_DELAY,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_WIND_THRESHOLD,
    DEFAULT_TEMP_MIN,
    DEFAULT_VALVE_DELAY,
)
from .coordinator import SprinklerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SprinklerCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    for zone_id in coordinator.zones:
        entities.append(ZoneDurationNumber(coordinator, entry, zone_id))
        entities.append(ZoneCycleDurationNumber(coordinator, entry, zone_id))
        entities.append(ZoneSoakDurationNumber(coordinator, entry, zone_id))
        entities.append(ZoneCycleCountNumber(coordinator, entry, zone_id))

    entities.append(RainThresholdNumber(coordinator, entry))
    entities.append(WindThresholdNumber(coordinator, entry))
    entities.append(FreezeThresholdNumber(coordinator, entry))
    entities.append(ValveDelayNumber(coordinator, entry))

    async_add_entities(entities)


class ZoneDurationNumber(CoordinatorEntity, NumberEntity):
    """Default watering duration for a zone in seconds."""

    _attr_native_min_value = 60
    _attr_native_max_value = 7200
    _attr_native_step = 60
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        zone = coordinator.zones[zone_id]
        self._attr_name = f"{zone.name} Duration"
        self._attr_unique_id = f"{entry.entry_id}_zone_duration_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> float:
        zone = self.coordinator.zones.get(self._zone_id)
        return float(zone.default_duration) if zone else 600.0

    async def async_set_native_value(self, value: float) -> None:
        zone = self.coordinator.zones.get(self._zone_id)
        if zone:
            zone.default_duration = int(value)
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class ZoneCycleDurationNumber(CoordinatorEntity, NumberEntity):
    """Cycle duration for soak-and-cycle mode (seconds)."""

    _attr_native_min_value = 60
    _attr_native_max_value = 3600
    _attr_native_step = 60
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-refresh"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        zone = coordinator.zones[zone_id]
        self._attr_name = f"{zone.name} Cycle Duration"
        self._attr_unique_id = f"{entry.entry_id}_zone_cycle_duration_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> float:
        zone = self.coordinator.zones.get(self._zone_id)
        return float(zone.cycle_duration) if zone else 300.0

    async def async_set_native_value(self, value: float) -> None:
        zone = self.coordinator.zones.get(self._zone_id)
        if zone:
            zone.cycle_duration = int(value)
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class ZoneSoakDurationNumber(CoordinatorEntity, NumberEntity):
    """Soak pause between cycles (seconds)."""

    _attr_native_min_value = 60
    _attr_native_max_value = 3600
    _attr_native_step = 60
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-pause"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        zone = coordinator.zones[zone_id]
        self._attr_name = f"{zone.name} Soak Duration"
        self._attr_unique_id = f"{entry.entry_id}_zone_soak_duration_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> float:
        zone = self.coordinator.zones.get(self._zone_id)
        return float(zone.soak_duration) if zone else 300.0

    async def async_set_native_value(self, value: float) -> None:
        zone = self.coordinator.zones.get(self._zone_id)
        if zone:
            zone.soak_duration = int(value)
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class ZoneCycleCountNumber(CoordinatorEntity, NumberEntity):
    """Number of soak-and-cycle repetitions."""

    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:repeat"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        zone = coordinator.zones[zone_id]
        self._attr_name = f"{zone.name} Cycle Count"
        self._attr_unique_id = f"{entry.entry_id}_zone_cycle_count_{zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> float:
        zone = self.coordinator.zones.get(self._zone_id)
        return float(zone.cycle_count) if zone else 2.0

    async def async_set_native_value(self, value: float) -> None:
        zone = self.coordinator.zones.get(self._zone_id)
        if zone:
            zone.cycle_count = int(value)
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class RainThresholdNumber(CoordinatorEntity, NumberEntity):
    """Rain forecast threshold in mm — skip if forecast exceeds this."""

    _attr_native_min_value = 0.0
    _attr_native_max_value = 25.0
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "mm"
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:weather-rainy"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"{entry.data.get('controller_name', NAME)} Rain Threshold"
        self._attr_unique_id = f"{entry.entry_id}_rain_threshold"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> float:
        return float(self.coordinator.config.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD))

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.config[CONF_RAIN_THRESHOLD] = value
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class WindThresholdNumber(CoordinatorEntity, NumberEntity):
    """Wind speed threshold — skip if wind exceeds this."""

    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = "km/h"
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:weather-windy"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"{entry.data.get('controller_name', NAME)} Wind Threshold"
        self._attr_unique_id = f"{entry.entry_id}_wind_threshold"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> float:
        return float(self.coordinator.config.get(CONF_WIND_THRESHOLD, DEFAULT_WIND_THRESHOLD))

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.config[CONF_WIND_THRESHOLD] = value
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class FreezeThresholdNumber(CoordinatorEntity, NumberEntity):
    """Freeze protection threshold — skip if temperature is at or below this."""

    _attr_native_min_value = -10.0
    _attr_native_max_value = 10.0
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:snowflake-thermometer"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"{entry.data.get('controller_name', NAME)} Freeze Threshold"
        self._attr_unique_id = f"{entry.entry_id}_freeze_threshold"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> float:
        return float(self.coordinator.config.get(CONF_TEMP_MIN, DEFAULT_TEMP_MIN))

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.config[CONF_TEMP_MIN] = value
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class ValveDelayNumber(CoordinatorEntity, NumberEntity):
    """Seconds to wait after pump/master ON before opening the zone valve."""

    _attr_native_min_value = 0
    _attr_native_max_value = 120
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-play-outline"

    def __init__(self, coordinator: SprinklerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_name = f"{entry.data.get('controller_name', NAME)} Valve Delay"
        self._attr_unique_id = f"{entry.entry_id}_valve_delay"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get("controller_name", NAME),
            manufacturer="Smart Sprinkler",
            model="Sprinkler Controller",
        )

    @property
    def native_value(self) -> float:
        return float(self.coordinator.config.get(CONF_VALVE_DELAY, DEFAULT_VALVE_DELAY))

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.config[CONF_VALVE_DELAY] = int(value)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
