"""Number platform for Smart Heating."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DEFAULT_SAFETY_MARGIN
from .coordinator import SmartHeatingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SmartHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    zone = coordinator.zone_name

    async_add_entities([
        SmartHeatingMarginNumber(coordinator, zone),
        SmartHeatingWarmupNumber(coordinator, zone),
    ])


class SmartHeatingMarginNumber(CoordinatorEntity[SmartHeatingCoordinator], NumberEntity):
    """Safety margin adjustment."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator)
        self._zone = zone
        self._attr_unique_id = f"smart_heating_{zone}_margin"
        self._attr_has_entity_name = True
        self._attr_name = "Marge de sécurité"
        self._attr_icon = "mdi:shield-half-full"
        self._attr_native_min_value = 100
        self._attr_native_max_value = 150
        self._attr_native_step = 5
        self._attr_native_unit_of_measurement = "%"
        self._attr_mode = NumberMode.SLIDER

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"smart_heating_{self._zone}")},
            "name": f"Smart Heating {self._zone.title()}",
        }

    @property
    def native_value(self) -> float:
        return round(self.coordinator.safety_margin * 100)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.safety_margin = value / 100.0
        await self.coordinator.async_request_refresh()


class SmartHeatingWarmupNumber(CoordinatorEntity[SmartHeatingCoordinator], NumberEntity):
    """Warmup ignore minutes adjustment."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator)
        self._zone = zone
        self._attr_unique_id = f"smart_heating_{zone}_warmup"
        self._attr_has_entity_name = True
        self._attr_name = "Temps montée en puissance"
        self._attr_icon = "mdi:fire-circle"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 30
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "min"
        self._attr_mode = NumberMode.SLIDER

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"smart_heating_{self._zone}")},
            "name": f"Smart Heating {self._zone.title()}",
        }

    @property
    def native_value(self) -> float:
        return self.coordinator.warmup_ignore_min

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.warmup_ignore_min = value
        self.coordinator.thermal_model.warmup_ignore_min = value
