"""Switch platform for Smart Heating."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartHeatingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SmartHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    zone = coordinator.zone_name

    async_add_entities([
        SmartHeatingEnabledSwitch(coordinator, zone),
        SmartHeatingLLMSwitch(coordinator, zone),
    ])


class SmartHeatingEnabledSwitch(CoordinatorEntity[SmartHeatingCoordinator], SwitchEntity):
    """Enable/disable Smart Heating for this zone."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator)
        self._zone = zone
        self._attr_unique_id = f"smart_heating_{zone}_enabled"
        self._attr_has_entity_name = True
        self._attr_name = "Activé"
        self._attr_icon = "mdi:brain"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"smart_heating_{self._zone}")},
            "name": f"Smart Heating {self._zone.title()}",
        }

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.enabled = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.enabled = False
        self.async_write_ha_state()


class SmartHeatingLLMSwitch(CoordinatorEntity[SmartHeatingCoordinator], SwitchEntity):
    """Enable/disable LLM calls for this zone."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator)
        self._zone = zone
        self._attr_unique_id = f"smart_heating_{zone}_llm_enabled"
        self._attr_has_entity_name = True
        self._attr_name = "IA activée"
        self._attr_icon = "mdi:robot"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"smart_heating_{self._zone}")},
            "name": f"Smart Heating {self._zone.title()}",
        }

    @property
    def is_on(self) -> bool:
        return self.coordinator.llm_enabled

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.llm_enabled = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.llm_enabled = False
        self.async_write_ha_state()
