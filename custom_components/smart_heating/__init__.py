"""Smart Heating - Intelligent heating anticipation for Home Assistant."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .const import DOMAIN, PLATFORMS
from .coordinator import SmartHeatingCoordinator

_LOGGER = logging.getLogger(__name__)

type SmartHeatingConfigEntry = ConfigEntry[SmartHeatingCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SmartHeatingConfigEntry) -> bool:
    """Set up Smart Heating from a config entry."""
    _LOGGER.info("Setting up Smart Heating zone: %s", entry.data.get("zone_name", "unknown"))

    coordinator = SmartHeatingCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options flow
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmartHeatingConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Smart Heating zone: %s", entry.data.get("zone_name", "unknown"))

    coordinator: SmartHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
