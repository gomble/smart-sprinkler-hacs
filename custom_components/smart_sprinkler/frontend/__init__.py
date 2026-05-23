"""Frontend card registration for Smart Sprinkler."""
from __future__ import annotations

import logging
import os

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from ..const import DOMAIN, URL_BASE, SMART_SPRINKLER_CARDS

_LOGGER = logging.getLogger(__name__)

_REGISTERED = False


class SprinklerCardRegistration:
    """Register the Lovelace card as a static resource."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def async_register(self) -> None:
        global _REGISTERED
        if _REGISTERED:
            return
        _REGISTERED = True

        www_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "www")

        try:
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(URL_BASE, www_path, cache_headers=False)]
            )
        except Exception:
            _LOGGER.debug("Static path %s already registered", URL_BASE)

        for card in SMART_SPRINKLER_CARDS:
            url = f"{URL_BASE}/{card['filename']}?v={card['version']}"
            add_extra_js_url(self.hass, url)
            _LOGGER.info("Registered card: %s", url)

    async def async_unregister(self) -> None:
        pass
