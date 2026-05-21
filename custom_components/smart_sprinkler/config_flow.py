"""Config flow for Smart Sprinkler."""
from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    NAME,
    CONF_CONTROLLER_NAME,
    CONF_ZONES,
    CONF_ZONE_NAME,
    CONF_PUMP_SWITCH,
    CONF_MASTER_SWITCH,
    CONF_WEATHER_ENTITY,
    CONF_RAIN_THRESHOLD,
    CONF_WIND_THRESHOLD,
    CONF_TEMP_MIN,
    CONF_ENABLE_WEATHER,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_WIND_THRESHOLD,
    DEFAULT_TEMP_MIN,
)


class SmartSprinklerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._zones: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 1: Controller basics."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_safety()

        schema = vol.Schema(
            {
                vol.Required(CONF_CONTROLLER_NAME, default="My Garden"): str,
                vol.Optional(CONF_PUMP_SWITCH, default=""): str,
                vol.Optional(CONF_MASTER_SWITCH, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_safety(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 2: Weather / safety settings."""
        if user_input is not None:
            # Clean up empty optional fields
            for key in [CONF_PUMP_SWITCH, CONF_MASTER_SWITCH, CONF_WEATHER_ENTITY]:
                val = self._data.get(key, "") or user_input.get(key, "")
                if val == "":
                    self._data.pop(key, None)
                    user_input.pop(key, None)
            self._data.update(user_input)
            return await self.async_step_zone()

        schema = vol.Schema(
            {
                vol.Optional(CONF_WEATHER_ENTITY, default=""): str,
                vol.Optional(CONF_ENABLE_WEATHER, default=True): bool,
                vol.Optional(CONF_RAIN_THRESHOLD, default=DEFAULT_RAIN_THRESHOLD): vol.Coerce(float),
                vol.Optional(CONF_WIND_THRESHOLD, default=DEFAULT_WIND_THRESHOLD): vol.Coerce(float),
                vol.Optional(CONF_TEMP_MIN, default=DEFAULT_TEMP_MIN): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="safety", data_schema=schema)

    async def async_step_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 3: Add a zone."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get("add_another", False):
                self._zones.append(self._build_zone(user_input))
                return await self.async_step_zone()

            self._zones.append(self._build_zone(user_input))
            self._data[CONF_ZONES] = self._zones
            return self.async_create_entry(
                title=self._data[CONF_CONTROLLER_NAME],
                data=self._data,
            )

        zone_num = len(self._zones) + 1
        schema = vol.Schema(
            {
                vol.Required(CONF_ZONE_NAME, default=f"Zone {zone_num}"): str,
                vol.Optional("switch_entity", default=""): str,
                vol.Optional("default_duration", default=600): vol.All(int, vol.Range(min=60, max=7200)),
                vol.Optional("enabled", default=True): bool,
                vol.Optional("add_another", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="zone",
            data_schema=schema,
            errors=errors,
            description_placeholders={"zone_num": str(zone_num)},
        )

    def _build_zone(self, data: dict) -> dict:
        return {
            "zone_id": str(uuid.uuid4())[:8],
            "zone_name": data[CONF_ZONE_NAME],
            "switch_entity": data.get("switch_entity") or None,
            "default_duration": data.get("default_duration", 600),
            "enabled": data.get("enabled", True),
            "schedule": {},
            "soak_cycle_enabled": False,
            "cycle_duration": 300,
            "soak_duration": 300,
            "cycle_count": 2,
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return SmartSprinklerOptionsFlow(config_entry)


class SmartSprinklerOptionsFlow(config_entries.OptionsFlow):
    """Options flow — edit controller settings and zones after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry
        self._data: dict[str, Any] = dict(config_entry.data)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Main options menu."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._data)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_WEATHER_ENTITY,
                    default=self._data.get(CONF_WEATHER_ENTITY, ""),
                ): str,
                vol.Optional(
                    CONF_ENABLE_WEATHER,
                    default=self._data.get(CONF_ENABLE_WEATHER, True),
                ): bool,
                vol.Optional(
                    CONF_RAIN_THRESHOLD,
                    default=self._data.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_WIND_THRESHOLD,
                    default=self._data.get(CONF_WIND_THRESHOLD, DEFAULT_WIND_THRESHOLD),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_TEMP_MIN,
                    default=self._data.get(CONF_TEMP_MIN, DEFAULT_TEMP_MIN),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_PUMP_SWITCH,
                    default=self._data.get(CONF_PUMP_SWITCH, ""),
                ): str,
                vol.Optional(
                    CONF_MASTER_SWITCH,
                    default=self._data.get(CONF_MASTER_SWITCH, ""),
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
