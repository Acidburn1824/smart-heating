"""Binary sensor platform for Smart Heating."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
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
        SmartHeatingAnticipatingBinary(coordinator, zone),
        SmartHeatingAntiCycleBinary(coordinator, zone),
    ])


class SmartHeatingBinaryBase(CoordinatorEntity[SmartHeatingCoordinator], BinarySensorEntity):
    def __init__(self, coordinator, zone, key):
        super().__init__(coordinator)
        self._zone = zone
        self._attr_unique_id = f"smart_heating_{zone}_{key}"
        self._attr_has_entity_name = True

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"smart_heating_{self._zone}")},
            "name": f"Smart Heating {self._zone.title()}",
        }


class SmartHeatingAnticipatingBinary(SmartHeatingBinaryBase):
    """Is anticipation currently active?"""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "anticipating")
        self._attr_name = "Anticipation active"
        self._attr_icon = "mdi:clock-fast"

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        return data.get("anticipation_active", False)


class SmartHeatingAntiCycleBinary(SmartHeatingBinaryBase):
    """Is anti-cycle preventing restart?"""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "anti_cycle")
        self._attr_name = "Anti-cycle actif"
        self._attr_icon = "mdi:shield-lock"

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        return data.get("anti_cycle_active", False)
