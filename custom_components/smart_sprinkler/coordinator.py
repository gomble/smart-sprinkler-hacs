"""DataUpdateCoordinator for Smart Sprinkler."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    STATUS_IDLE,
    STATUS_WAITING,
    STATUS_RUNNING,
    STATUS_RAIN_DELAY,
    STATUS_SUSPENDED,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_WIND_THRESHOLD,
    DEFAULT_TEMP_MIN,
    DEFAULT_VALVE_DELAY,
    CONF_VALVE_DELAY,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)


class SprinklerCoordinator(DataUpdateCoordinator):
    """Manage state for a single sprinkler controller."""

    def __init__(self, hass: HomeAssistant, entry_id: str, config: dict) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry_id}",
            update_interval=UPDATE_INTERVAL,
        )
        self.entry_id = entry_id
        self.config = config
        self.zones: dict[str, ZoneState] = {}
        self.status: str = STATUS_IDLE
        self.rain_delay_until: datetime | None = None
        self.active_zone_id: str | None = None
        self._active_task: asyncio.Task | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._scheduler_task: asyncio.Task | None = None
        self.weather_skip_reason: str | None = None
        self.total_water_time_today: int = 0  # seconds
        self._last_date_reset: datetime | None = None
        self.valve_delay_remaining: int = 0   # countdown shown in UI while waiting

        # Build initial zone states from config
        for zone_cfg in config.get("zones", []):
            zid = zone_cfg["zone_id"]
            self.zones[zid] = ZoneState(zid, zone_cfg)

    async def _async_update_data(self) -> dict[str, Any]:
        """Periodic update — refresh weather check and daily counters."""
        now = dt_util.now()

        # Reset daily water counters at midnight
        if self._last_date_reset is None or self._last_date_reset.date() < now.date():
            self.total_water_time_today = 0
            for zone in self.zones.values():
                zone.water_time_today = 0
            self._last_date_reset = now

        # Lift rain delay if expired
        if self.rain_delay_until and now > self.rain_delay_until:
            self.rain_delay_until = None
            if self.status == STATUS_RAIN_DELAY:
                self.status = STATUS_IDLE

        return {
            "status": self.status,
            "zones": {zid: z.as_dict() for zid, z in self.zones.items()},
            "rain_delay_until": self.rain_delay_until,
            "active_zone": self.active_zone_id,
            "total_water_time_today": self.total_water_time_today,
            "weather_skip_reason": self.weather_skip_reason,
            "valve_delay_remaining": self.valve_delay_remaining,
        }

    # ------------------------------------------------------------------
    # Weather helpers
    # ------------------------------------------------------------------

    async def async_check_weather(self) -> tuple[bool, str | None]:
        """Return (should_skip, reason). Checks forecast from weather entity."""
        weather_entity = self.config.get("weather_entity")
        if not weather_entity or not self.config.get("enable_weather", True):
            return False, None

        state = self.hass.states.get(weather_entity)
        if state is None:
            return False, None

        rain_threshold = self.config.get("rain_threshold", DEFAULT_RAIN_THRESHOLD)
        wind_threshold = self.config.get("wind_threshold", DEFAULT_WIND_THRESHOLD)
        temp_min = self.config.get("temp_min", DEFAULT_TEMP_MIN)

        # Current conditions
        attrs = state.attributes
        wind_speed = attrs.get("wind_speed", 0) or 0
        temp = attrs.get("temperature", 99) or 99

        if temp <= temp_min:
            return True, f"freeze_protection (temp {temp}°C)"

        if wind_speed >= wind_threshold:
            return True, f"high_wind ({wind_speed} km/h)"

        # Check forecast for precipitation
        forecast = attrs.get("forecast", [])
        for day in forecast[:2]:  # next 2 forecast periods
            precip = day.get("precipitation", 0) or 0
            if precip >= rain_threshold:
                return True, f"rain_forecast ({precip} mm)"

        return False, None

    # ------------------------------------------------------------------
    # Zone control
    # ------------------------------------------------------------------

    async def async_start_zone(self, zone_id: str, duration_seconds: int) -> None:
        """Start a single zone for the given duration.

        Sequence: pump/master ON → wait valve_delay → zone valve ON → run timer.
        """
        if zone_id not in self.zones:
            _LOGGER.error("Zone %s not found", zone_id)
            return

        # Stop any currently running zone first
        await self.async_stop_all()

        zone = self.zones[zone_id]
        self.active_zone_id = zone_id

        # Activate pump/master if configured
        await self._async_set_pump(True)
        await self._async_set_master(True)

        # Wait for valve delay before opening the zone valve
        delay = int(self.config.get(CONF_VALVE_DELAY, DEFAULT_VALVE_DELAY))
        if delay > 0:
            self.status = STATUS_WAITING
            self.valve_delay_remaining = delay
            self.async_set_updated_data(await self._async_update_data())

            for remaining in range(delay, 0, -1):
                await asyncio.sleep(1)
                self.valve_delay_remaining = remaining - 1
            self.valve_delay_remaining = 0

        # Now open the zone valve
        self.status = STATUS_RUNNING
        zone.is_running = True
        zone.remaining_seconds = duration_seconds
        zone.started_at = dt_util.now()

        if zone.switch_entity:
            await self.hass.services.async_call(
                "switch", "turn_on", {"entity_id": zone.switch_entity}
            )

        self.async_set_updated_data(await self._async_update_data())

        # Schedule auto-stop
        self._active_task = self.hass.async_create_task(
            self._async_run_zone_timer(zone_id, duration_seconds)
        )

    async def _async_run_zone_timer(self, zone_id: str, duration_seconds: int) -> None:
        """Count down and stop zone when duration expires."""
        try:
            zone = self.zones[zone_id]
            elapsed = 0
            while elapsed < duration_seconds:
                await asyncio.sleep(1)
                elapsed += 1
                zone.remaining_seconds = duration_seconds - elapsed
            await self.async_stop_zone(zone_id)
        except asyncio.CancelledError:
            pass

    async def async_stop_zone(self, zone_id: str) -> None:
        """Stop a specific zone."""
        if zone_id not in self.zones:
            return
        zone = self.zones[zone_id]
        if zone.switch_entity:
            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": zone.switch_entity}
            )

        if zone.started_at:
            elapsed = int((dt_util.now() - zone.started_at).total_seconds())
            zone.water_time_today += elapsed
            self.total_water_time_today += elapsed
            zone.last_run = dt_util.now()

        zone.is_running = False
        zone.remaining_seconds = 0
        zone.started_at = None

        if self.active_zone_id == zone_id:
            self.active_zone_id = None
            self.status = STATUS_IDLE
            await self._async_set_pump(False)
            await self._async_set_master(False)

        self.async_set_updated_data(await self._async_update_data())

    async def async_stop_all(self) -> None:
        """Stop all running zones (also cancels an active valve delay)."""
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        for zone_id, zone in self.zones.items():
            if zone.is_running:
                await self.async_stop_zone(zone_id)
        self.status = STATUS_IDLE
        self.active_zone_id = None
        self.valve_delay_remaining = 0
        await self._async_set_pump(False)
        await self._async_set_master(False)
        self.async_set_updated_data(await self._async_update_data())

    async def async_set_rain_delay(self, days: int) -> None:
        """Suspend watering for N days."""
        self.rain_delay_until = dt_util.now() + timedelta(days=days)
        self.status = STATUS_RAIN_DELAY
        await self.async_stop_all()
        self.async_set_updated_data(await self._async_update_data())

    # ------------------------------------------------------------------
    # Pump / master valve helpers
    # ------------------------------------------------------------------

    async def _async_set_pump(self, on: bool) -> None:
        pump = self.config.get("pump_switch")
        if pump:
            svc = "turn_on" if on else "turn_off"
            await self.hass.services.async_call("switch", svc, {"entity_id": pump})

    async def _async_set_master(self, on: bool) -> None:
        master = self.config.get("master_switch")
        if master:
            svc = "turn_on" if on else "turn_off"
            await self.hass.services.async_call("switch", svc, {"entity_id": master})


class ZoneState:
    """Runtime state for a single zone."""

    def __init__(self, zone_id: str, config: dict) -> None:
        self.zone_id = zone_id
        self.name: str = config.get("zone_name", f"Zone {zone_id}")
        self.switch_entity: str | None = config.get("switch_entity")
        self.is_running: bool = False
        self.is_enabled: bool = config.get("enabled", True)
        self.remaining_seconds: int = 0
        self.water_time_today: int = 0
        self.last_run: datetime | None = None
        self.next_run: datetime | None = None
        self.started_at: datetime | None = None
        self.schedule: dict = config.get("schedule", {})
        self.default_duration: int = config.get("default_duration", 600)  # seconds
        self.soak_cycle_enabled: bool = config.get("soak_cycle_enabled", False)
        self.cycle_duration: int = config.get("cycle_duration", 300)
        self.soak_duration: int = config.get("soak_duration", 300)
        self.cycle_count: int = config.get("cycle_count", 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "name": self.name,
            "switch_entity": self.switch_entity,
            "is_running": self.is_running,
            "is_enabled": self.is_enabled,
            "remaining_seconds": self.remaining_seconds,
            "water_time_today": self.water_time_today,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "default_duration": self.default_duration,
            "schedule": self.schedule,
        }
