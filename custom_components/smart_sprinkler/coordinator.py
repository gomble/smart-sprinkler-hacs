"""DataUpdateCoordinator for Smart Sprinkler."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    STATUS_IDLE,
    STATUS_WAITING,
    STATUS_RUNNING,
    STATUS_STOPPING,
    STATUS_RAIN_DELAY,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_WIND_THRESHOLD,
    DEFAULT_TEMP_MIN,
    DEFAULT_VALVE_DELAY,
    CONF_VALVE_DELAY,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)


class SprinklerCoordinator(DataUpdateCoordinator):
    """Manage state for a single sprinkler controller.

    Multiple zones can run simultaneously.
    - Startup delay runs once when the FIRST zone activates (pump was off).
    - Shutdown delay runs once when the LAST zone stops (pump goes off).
    - Zones started while others are already running skip the startup delay.
    """

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
        self._zone_tasks: dict[str, asyncio.Task] = {}
        self._shutdown_task: asyncio.Task | None = None
        self.weather_skip_reason: str | None = None
        self.total_water_time_today: int = 0
        self._last_date_reset: datetime | None = None
        self.valve_delay_remaining: int = 0

        for zone_cfg in config.get("zones", []):
            zid = zone_cfg["zone_id"]
            self.zones[zid] = ZoneState(zid, zone_cfg)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def active_zone_ids(self) -> list[str]:
        return [
            zid for zid, z in self.zones.items()
            if z.is_running or z.is_activating
        ]

    @property
    def _pump_should_be_on(self) -> bool:
        """True if at least one zone is active (activating or running)."""
        return bool(self.active_zone_ids)

    # ------------------------------------------------------------------
    # Coordinator update
    # ------------------------------------------------------------------

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
            "active_zones": self.active_zone_ids,
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

        for day in (attrs.get("forecast") or [])[:2]:
            precip = day.get("precipitation", 0) or 0
            if precip >= rain_threshold:
                return True, f"rain_forecast ({precip} mm)"

        return False, None

    # ------------------------------------------------------------------
    # Public zone control
    # ------------------------------------------------------------------

    async def async_start_zone(self, zone_id: str, duration_seconds: int) -> None:
        """Start a zone. Multiple zones can run at the same time.

        Startup delay only fires when this is the first zone (pump was off).
        If zones are already running the valve opens immediately.
        """
        if zone_id not in self.zones:
            _LOGGER.error("Zone %s not found", zone_id)
            return

        # Cancel any pending shutdown so pump stays on
        if self._shutdown_task and not self._shutdown_task.done():
            self._shutdown_task.cancel()
            self._shutdown_task = None

        # Cancel existing task for this specific zone if it is somehow still running
        await self._cancel_zone_task(zone_id)

        zone = self.zones[zone_id]
        is_first_zone = not self._pump_should_be_on  # check BEFORE marking activating

        # Mark zone as activating immediately → switch shows ON right away
        zone.is_activating = True

        if is_first_zone:
            await self._async_set_pump(True)
            await self._async_set_master(True)

        self.async_set_updated_data(await self._async_update_data())

        self._zone_tasks[zone_id] = self.hass.async_create_task(
            self._async_run_zone(zone_id, duration_seconds, apply_startup_delay=is_first_zone)
        )

    async def async_stop_zone(self, zone_id: str) -> None:
        """Stop a specific zone. Pump/master only off when last zone stops."""
        await self._cancel_zone_task(zone_id)
        await self._async_close_zone_valve(zone_id)
        await self._async_maybe_shutdown()
        self.async_set_updated_data(await self._async_update_data())

    async def async_stop_all(self, skip_shutdown_delay: bool = False) -> None:
        """Stop all running zones immediately."""
        # Cancel all zone tasks
        for zone_id in list(self._zone_tasks):
            await self._cancel_zone_task(zone_id)

        # Cancel pending shutdown too
        if self._shutdown_task and not self._shutdown_task.done():
            self._shutdown_task.cancel()
            self._shutdown_task = None

        for zone in self.zones.values():
            if zone.is_running or zone.is_activating:
                await self._async_close_zone_valve(zone.zone_id)

        self.valve_delay_remaining = 0

        if skip_shutdown_delay:
            self.status = STATUS_IDLE
            await self._async_set_pump(False)
            await self._async_set_master(False)
        else:
            await self._async_do_shutdown()

        self.async_set_updated_data(await self._async_update_data())

    async def async_set_rain_delay(self, days: int) -> None:
        self.rain_delay_until = dt_util.now() + timedelta(days=days)
        self.status = STATUS_RAIN_DELAY
        await self.async_stop_all()
        self.async_set_updated_data(await self._async_update_data())

    # ------------------------------------------------------------------
    # Internal — per-zone sequence task
    # ------------------------------------------------------------------

    async def _async_run_zone(
        self, zone_id: str, duration_seconds: int, apply_startup_delay: bool
    ) -> None:
        """Full zone lifecycle as a cancellable task."""
        zone = self.zones[zone_id]
        delay = int(self.config.get(CONF_VALVE_DELAY, DEFAULT_VALVE_DELAY))

        try:
            # ── Startup delay (only for first zone) ───────────────────
            if apply_startup_delay and delay > 0:
                self.status = STATUS_WAITING
                self.valve_delay_remaining = delay
                self.async_set_updated_data(await self._async_update_data())

                for tick in range(delay):
                    await asyncio.sleep(1)
                    self.valve_delay_remaining = delay - tick - 1

                self.valve_delay_remaining = 0

            # ── Open zone valve ───────────────────────────────────────
            zone.is_activating = False
            zone.is_running = True
            zone.remaining_seconds = duration_seconds
            zone.started_at = dt_util.now()
            self._update_controller_status()

            if zone.switch_entity:
                await self.hass.services.async_call(
                    "switch", "turn_on", {"entity_id": zone.switch_entity}
                )

            self.async_set_updated_data(await self._async_update_data())

            # ── Run timer ─────────────────────────────────────────────
            for elapsed in range(1, duration_seconds + 1):
                await asyncio.sleep(1)
                zone.remaining_seconds = duration_seconds - elapsed

            # ── Close valve ───────────────────────────────────────────
            await self._async_close_zone_valve(zone_id)
            self._zone_tasks.pop(zone_id, None)

            # ── Shutdown if this was the last zone ────────────────────
            await self._async_maybe_shutdown()
            self.async_set_updated_data(await self._async_update_data())

        except asyncio.CancelledError:
            zone.is_activating = False
            raise

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    async def _cancel_zone_task(self, zone_id: str) -> None:
        task = self._zone_tasks.pop(zone_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _async_close_zone_valve(self, zone_id: str) -> None:
        """Close a zone valve and record stats. Never touches pump/master."""
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

    async def _async_maybe_shutdown(self) -> None:
        """Trigger shutdown sequence only if no zones are active anymore."""
        if self._pump_should_be_on:
            # Other zones still running — just update status
            self._update_controller_status()
            return
        self._shutdown_task = self.hass.async_create_task(self._async_do_shutdown())

    async def _async_do_shutdown(self) -> None:
        """Shutdown delay then pump/master off — runs as a cancellable task."""
        delay = int(self.config.get(CONF_VALVE_DELAY, DEFAULT_VALVE_DELAY))

        try:
            if delay > 0:
                self.status = STATUS_STOPPING
                self.valve_delay_remaining = delay
                self.async_set_updated_data(await self._async_update_data())

                for tick in range(delay):
                    await asyncio.sleep(1)
                    self.valve_delay_remaining = delay - tick - 1

                self.valve_delay_remaining = 0

            self.status = STATUS_IDLE
            await self._async_set_pump(False)
            await self._async_set_master(False)

        except asyncio.CancelledError:
            # A new zone was started — pump stays on
            raise

    def _update_controller_status(self) -> None:
        """Set status based on what is currently active."""
        if any(z.is_activating for z in self.zones.values()):
            self.status = STATUS_WAITING
        elif any(z.is_running for z in self.zones.values()):
            self.status = STATUS_RUNNING
        else:
            self.status = STATUS_IDLE

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
        self.is_activating: bool = False
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
