"""Config flow for Smart Sprinkler."""
from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    NAME,
    CONF_CONTROLLER_NAME,
    CONF_ZONES,
    CONF_ZONE_NAME,
    CONF_PUMP_SWITCH,
    CONF_MASTER_SWITCH,
    CONF_VALVE_DELAY,
    CONF_WEATHER_ENTITY,
    CONF_RAIN_THRESHOLD,
    CONF_WIND_THRESHOLD,
    CONF_TEMP_MIN,
    CONF_ENABLE_WEATHER,
    DEFAULT_VALVE_DELAY,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_WIND_THRESHOLD,
    DEFAULT_TEMP_MIN,
)

# ──────────────────────────────────────────────────────────────────────────────
# Initial config flow (first-time setup)
# ──────────────────────────────────────────────────────────────────────────────

class SmartSprinklerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Three-step setup: controller → weather/safety → zones."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._zones: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 1: Controller name + pump / master / valve delay."""
        if user_input is not None:
            for key in (CONF_PUMP_SWITCH, CONF_MASTER_SWITCH):
                if not user_input.get(key):
                    user_input.pop(key, None)
            self._data.update(user_input)
            return await self.async_step_safety()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_CONTROLLER_NAME, default="My Garden"): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Optional(CONF_PUMP_SWITCH): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="switch")
                ),
                vol.Optional(CONF_MASTER_SWITCH): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="switch")
                ),
                vol.Optional(CONF_VALVE_DELAY, default=DEFAULT_VALVE_DELAY): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=120, step=1, unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }),
        )

    async def async_step_safety(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 2: Weather entity + safety thresholds."""
        if user_input is not None:
            if not user_input.get(CONF_WEATHER_ENTITY):
                user_input.pop(CONF_WEATHER_ENTITY, None)
            self._data.update(user_input)
            return await self.async_step_zone()

        return self.async_show_form(
            step_id="safety",
            data_schema=vol.Schema({
                vol.Optional(CONF_WEATHER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather")
                ),
                vol.Optional(CONF_ENABLE_WEATHER, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_RAIN_THRESHOLD, default=DEFAULT_RAIN_THRESHOLD): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=25, step=0.5, unit_of_measurement="mm", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_WIND_THRESHOLD, default=DEFAULT_WIND_THRESHOLD): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=120, step=1, unit_of_measurement="km/h", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(CONF_TEMP_MIN, default=DEFAULT_TEMP_MIN): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=-10, max=10, step=0.5, unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX)
                ),
            }),
        )

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 3: Add zones (repeatable)."""
        if user_input is not None:
            add_another = user_input.pop("add_another", False)
            if not user_input.get("switch_entity"):
                user_input.pop("switch_entity", None)
            self._zones.append(_build_zone(user_input))
            if add_another:
                return await self.async_step_zone()
            self._data[CONF_ZONES] = self._zones
            return self.async_create_entry(title=self._data[CONF_CONTROLLER_NAME], data=self._data)

        zone_num = len(self._zones) + 1
        return self.async_show_form(
            step_id="zone",
            data_schema=_zone_schema(),
            description_placeholders={"zone_num": str(zone_num)},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return SmartSprinklerOptionsFlow(config_entry)


# ──────────────────────────────────────────────────────────────────────────────
# Options flow — edit everything after setup
# ──────────────────────────────────────────────────────────────────────────────

class SmartSprinklerOptionsFlow(config_entries.OptionsFlow):
    """Menu-driven options: controller settings + full zone management."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry
        # Work on a mutable copy; zones list is kept separately for easy editing
        merged = {**config_entry.data, **config_entry.options}
        self._data: dict[str, Any] = {k: v for k, v in merged.items() if k != CONF_ZONES}
        self._zones: list[dict] = list(merged.get(CONF_ZONES, []))
        self._edit_zone_index: int | None = None   # which zone is being edited

    # ── Main menu ────────────────────────────────────────────────────────────

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Top-level menu: choose what to edit."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "controller":
                return await self.async_step_controller()
            if action == "zones":
                return await self.async_step_zones_menu()
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("action", default="controller"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": "controller", "label": "Controller & Weather Settings"},
                            {"value": "zones", "label": "Manage Zones"},
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
        )

    # ── Controller settings ───────────────────────────────────────────────────

    async def async_step_controller(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Edit controller name, pump, master, valve delay, weather."""
        if user_input is not None:
            for key in (CONF_WEATHER_ENTITY, CONF_PUMP_SWITCH, CONF_MASTER_SWITCH):
                if not user_input.get(key):
                    user_input.pop(key, None)
            self._data.update(user_input)
            return self._save()

        return self.async_show_form(
            step_id="controller",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_CONTROLLER_NAME,
                    default=self._data.get(CONF_CONTROLLER_NAME, "My Garden"),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                ),
                vol.Optional(
                    CONF_PUMP_SWITCH,
                    description={"suggested_value": self._data.get(CONF_PUMP_SWITCH)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="switch")),
                vol.Optional(
                    CONF_MASTER_SWITCH,
                    description={"suggested_value": self._data.get(CONF_MASTER_SWITCH)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="switch")),
                vol.Optional(
                    CONF_VALVE_DELAY,
                    default=self._data.get(CONF_VALVE_DELAY, DEFAULT_VALVE_DELAY),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=120, step=1, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_WEATHER_ENTITY,
                    description={"suggested_value": self._data.get(CONF_WEATHER_ENTITY)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
                vol.Optional(
                    CONF_ENABLE_WEATHER,
                    default=self._data.get(CONF_ENABLE_WEATHER, True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_RAIN_THRESHOLD,
                    default=self._data.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=25, step=0.5, unit_of_measurement="mm", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_WIND_THRESHOLD,
                    default=self._data.get(CONF_WIND_THRESHOLD, DEFAULT_WIND_THRESHOLD),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=120, step=1, unit_of_measurement="km/h", mode=selector.NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_TEMP_MIN,
                    default=self._data.get(CONF_TEMP_MIN, DEFAULT_TEMP_MIN),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=-10, max=10, step=0.5, unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX)
                ),
            }),
        )

    # ── Zone list menu ────────────────────────────────────────────────────────

    async def async_step_zones_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show zone list: pick a zone to edit/delete, or add a new one."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "add":
                self._edit_zone_index = None
                return await self.async_step_zone_edit()
            if action == "back":
                return await self.async_step_init()
            # Zone index encoded as "edit_N" or "delete_N"
            if action and action.startswith("edit_"):
                self._edit_zone_index = int(action.split("_")[1])
                return await self.async_step_zone_edit()
            if action and action.startswith("delete_"):
                idx = int(action.split("_")[1])
                self._zones.pop(idx)
                return self._save()

        zone_options = [
            {"value": f"edit_{i}", "label": f"✏  {z.get('zone_name', f'Zone {i+1}')}"}
            for i, z in enumerate(self._zones)
        ]
        zone_options += [
            {"value": "add",  "label": "＋  Add new zone"},
            {"value": "back", "label": "← Back"},
        ]

        return self.async_show_form(
            step_id="zones_menu",
            data_schema=vol.Schema({
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=zone_options,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }),
            description_placeholders={"zone_count": str(len(self._zones))},
        )

    # ── Zone edit / add ───────────────────────────────────────────────────────

    async def async_step_zone_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Edit an existing zone or create a new one."""
        editing = self._edit_zone_index is not None
        existing: dict = self._zones[self._edit_zone_index] if editing else {}

        if user_input is not None:
            if not user_input.get("switch_entity"):
                user_input.pop("switch_entity", None)

            if editing:
                # Preserve zone_id and runtime-only fields
                updated = {**existing, **user_input}
                updated["default_duration"] = int(user_input.get("default_duration", existing.get("default_duration", 600)))
                self._zones[self._edit_zone_index] = updated
            else:
                self._zones.append(_build_zone(user_input))

            return self._save()

        return self.async_show_form(
            step_id="zone_edit",
            data_schema=_zone_schema(existing),
            description_placeholders={
                "action": "Edit" if editing else "Add",
                "zone_name": existing.get("zone_name", "new zone"),
            },
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _save(self) -> config_entries.FlowResult:
        """Persist current state and trigger a reload."""
        return self.async_create_entry(
            title="",
            data={**self._data, CONF_ZONES: self._zones},
        )


# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────

def _zone_schema(existing: dict | None = None) -> vol.Schema:
    """Schema for zone add/edit form, pre-filled with existing values."""
    d = existing or {}
    return vol.Schema({
        vol.Required(CONF_ZONE_NAME, default=d.get("zone_name", "")): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        ),
        vol.Optional(
            "switch_entity",
            description={"suggested_value": d.get("switch_entity")},
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="switch")
        ),
        vol.Optional("default_duration", default=d.get("default_duration", 600)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=60, max=7200, step=60, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)
        ),
        vol.Optional("enabled", default=d.get("enabled", True)): selector.BooleanSelector(),
        # Only show "add another" when creating a new zone (no existing data)
        **({} if existing else {vol.Optional("add_another", default=False): selector.BooleanSelector()}),
    })


def _build_zone(data: dict) -> dict:
    return {
        "zone_id": str(uuid.uuid4())[:8],
        "zone_name": data[CONF_ZONE_NAME],
        "switch_entity": data.get("switch_entity") or None,
        "default_duration": int(data.get("default_duration", 600)),
        "enabled": data.get("enabled", True),
        "schedule": {},
        "soak_cycle_enabled": False,
        "cycle_duration": 300,
        "soak_duration": 300,
        "cycle_count": 2,
    }
