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
    STATUS_STOPPING,
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
        self.weather_skip_reason: str | None = None
        self.total_water_time_today: int = 0
        self._last_date_reset: datetime | None = None
        self.valve_delay_remaining: int = 0

        for zone_cfg in config.get("zones", []):
            zid = zone_cfg["zone_id"]
            self.zones[zid] = ZoneState(zid, zone_cfg)

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.now()

        if self._last_date_reset is None or self._last_date_reset.date() < now.date():
            self.total_water_time_today = 0
            for zone in self.zones.values():
                zone.water_time_today = 0
            self._last_date_reset = now

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
        weather_entity = self.config.get("weather_entity")
        if not weather_entity or not self.config.get("enable_weather", True):
            return False, None

        state = self.hass.states.get(weather_entity)
        if state is None:
            return False, None

        rain_threshold = self.config.get("rain_threshold", DEFAULT_RAIN_THRESHOLD)
        wind_threshold = self.config.get("wind_threshold", DEFAULT_WIND_THRESHOLD)
        temp_min = self.config.get("temp_min", DEFAULT_TEMP_MIN)

        attrs = state.attributes
        wind_speed = attrs.get("wind_speed", 0) or 0
        temp = attrs.get("temperature", 99) or 99

        if temp <= temp_min:
            return True, f"freeze_protection (temp {temp}°C)"
        if wind_speed >= wind_threshold:
            return True, f"high_wind ({wind_speed} km/h)"

        forecast = attrs.get("forecast", [])
        for day in forecast[:2]:
            precip = day.get("precipitation", 0) or 0
            if precip >= rain_threshold:
                return True, f"rain_forecast ({precip} mm)"

        return False, None

    # ------------------------------------------------------------------
    # Zone control — public API
    # ------------------------------------------------------------------

    async def async_start_zone(self, zone_id: str, duration_seconds: int) -> None:
        """Start a zone.

        Full sequence (all in _active_task so stop_all can cancel cleanly):
          pump/master ON → startup delay → zone valve ON → run → zone valve OFF
          → shutdown delay → pump/master OFF
        """
        if zone_id not in self.zones:
            _LOGGER.error("Zone %s not found", zone_id)
            return

        # Stop current zone without shutdown delay — pump stays on for the new zone
        await self.async_stop_all(skip_shutdown_delay=True)

        zone = self.zones[zone_id]
        self.active_zone_id = zone_id

        # Mark activating NOW so the switch entity shows ON immediately
        zone.is_activating = True

        await self._async_set_pump(True)
        await self._async_set_master(True)

        self.async_set_updated_data(await self._async_update_data())

        self._active_task = self.hass.async_create_task(
            self._async_run_zone_sequence(zone_id, duration_seconds)
        )

    async def async_stop_zone(self, zone_id: str) -> None:
        """Stop a specific zone (applies shutdown delay before pump/master off)."""
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
            try:
                await self._active_task
            except asyncio.CancelledError:
                pass

        await self._async_close_zone_valve(zone_id)

        if self.active_zone_id == zone_id:
            await self._async_shutdown_delay_and_pump_off()

        self.async_set_updated_data(await self._async_update_data())

    async def async_stop_all(self, skip_shutdown_delay: bool = False) -> None:
        """Stop all zones. skip_shutdown_delay=True when immediately starting a new zone."""
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
            try:
                await self._active_task
            except asyncio.CancelledError:
                pass

        for zone in self.zones.values():
            if zone.is_running or zone.is_activating:
                await self._async_close_zone_valve(zone.zone_id)

        self.valve_delay_remaining = 0

        if not skip_shutdown_delay:
            await self._async_shutdown_delay_and_pump_off()
        else:
            # Pump/master stay on — caller is about to start a new zone
            self.status = STATUS_IDLE
            self.active_zone_id = None

        self.async_set_updated_data(await self._async_update_data())

    async def async_set_rain_delay(self, days: int) -> None:
        self.rain_delay_until = dt_util.now() + timedelta(days=days)
        self.status = STATUS_RAIN_DELAY
        await self.async_stop_all()
        self.async_set_updated_data(await self._async_update_data())

    # ------------------------------------------------------------------
    # Internal — zone sequence task (cancellable)
    # ------------------------------------------------------------------

    async def _async_run_zone_sequence(self, zone_id: str, duration_seconds: int) -> None:
        """Full zone lifecycle — runs as a cancellable task."""
        zone = self.zones[zone_id]
        delay = int(self.config.get(CONF_VALVE_DELAY, DEFAULT_VALVE_DELAY))

        try:
            # ── Startup delay ──────────────────────────────────────────
            if delay > 0:
                self.status = STATUS_WAITING
                self.valve_delay_remaining = delay
                self.async_set_updated_data(await self._async_update_data())

                for tick in range(delay):
                    await asyncio.sleep(1)
                    self.valve_delay_remaining = delay - tick - 1

                self.valve_delay_remaining = 0

            # ── Open zone valve ────────────────────────────────────────
            zone.is_activating = False
            zone.is_running = True
            zone.remaining_seconds = duration_seconds
            zone.started_at = dt_util.now()
            self.status = STATUS_RUNNING

            if zone.switch_entity:
                await self.hass.services.async_call(
                    "switch", "turn_on", {"entity_id": zone.switch_entity}
                )

            self.async_set_updated_data(await self._async_update_data())

            # ── Run timer ─────────────────────────────────────────────
            for elapsed in range(1, duration_seconds + 1):
                await asyncio.sleep(1)
                zone.remaining_seconds = duration_seconds - elapsed

            # ── Close zone valve ───────────────────────────────────────
            await self._async_close_zone_valve(zone_id)

            # ── Shutdown delay then pump/master off ────────────────────
            await self._async_shutdown_delay_and_pump_off()

        except asyncio.CancelledError:
            # Called by stop_zone / stop_all — they handle cleanup
            zone.is_activating = False
            raise

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    async def _async_close_zone_valve(self, zone_id: str) -> None:
        """Close the zone valve and record water-time stats. Does NOT touch pump/master."""
        zone = self.zones.get(zone_id)
        if not zone:
            return

        if zone.switch_entity and (zone.is_running or zone.is_activating):
            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": zone.switch_entity}
            )

        if zone.started_at:
            elapsed = int((dt_util.now() - zone.started_at).total_seconds())
            zone.water_time_today += elapsed
            self.total_water_time_today += elapsed
            zone.last_run = dt_util.now()

        zone.is_running = False
        zone.is_activating = False
        zone.remaining_seconds = 0
        zone.started_at = None

    async def _async_shutdown_delay_and_pump_off(self) -> None:
        """Wait the configured delay, then turn off pump/master and go idle."""
        delay = int(self.config.get(CONF_VALVE_DELAY, DEFAULT_VALVE_DELAY))

        if delay > 0:
            self.status = STATUS_STOPPING
            self.valve_delay_remaining = delay
            self.async_set_updated_data(await self._async_update_data())

            for tick in range(delay):
                await asyncio.sleep(1)
                self.valve_delay_remaining = delay - tick - 1

            self.valve_delay_remaining = 0

        self.status = STATUS_IDLE
        self.active_zone_id = None
        await self._async_set_pump(False)
        await self._async_set_master(False)

    async def _async_set_pump(self, on: bool) -> None:
        pump = self.config.get("pump_switch")
        if pump:
            await self.hass.services.async_call(
                "switch", "turn_on" if on else "turn_off", {"entity_id": pump}
            )

    async def _async_set_master(self, on: bool) -> None:
        master = self.config.get("master_switch")
        if master:
            await self.hass.services.async_call(
                "switch", "turn_on" if on else "turn_off", {"entity_id": master}
            )


class ZoneState:
    """Runtime state for a single zone."""

    def __init__(self, zone_id: str, config: dict) -> None:
        self.zone_id = zone_id
        self.name: str = config.get("zone_name", f"Zone {zone_id}")
        self.switch_entity: str | None = config.get("switch_entity")
        self.is_running: bool = False
        self.is_activating: bool = False   # True during startup delay — switch shows ON
        self.is_enabled: bool = config.get("enabled", True)
        self.remaining_seconds: int = 0
        self.water_time_today: int = 0
        self.last_run: datetime | None = None
        self.next_run: datetime | None = None
        self.started_at: datetime | None = None
        self.schedule: dict = config.get("schedule", {})
        self.default_duration: int = config.get("default_duration", 600)
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
            "is_activating": self.is_activating,
            "is_enabled": self.is_enabled,
            "remaining_seconds": self.remaining_seconds,
            "water_time_today": self.water_time_today,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "default_duration": self.default_duration,
            "schedule": self.schedule,
        }
