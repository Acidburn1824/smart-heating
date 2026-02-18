"""Sensor platform for Smart Heating."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartHeatingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator: SmartHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]
    zone = coordinator.zone_name

    entities = [
        SmartHeatingStateSensor(coordinator, zone),
        SmartHeatingSessionsSensor(coordinator, zone),
        SmartHeatingMinPerDegSensor(coordinator, zone),
        SmartHeatingSpeedSensor(coordinator, zone),
        SmartHeatingAnticipationSensor(coordinator, zone),
        SmartHeatingLLMAdviceSensor(coordinator, zone),
        SmartHeatingEffectiveMarginSensor(coordinator, zone),
        SmartHeatingScheduleSensor(coordinator, zone),
        SmartHeatingFeedbackSensor(coordinator, zone),
    ]

    async_add_entities(entities)


class SmartHeatingSensorBase(CoordinatorEntity[SmartHeatingCoordinator], SensorEntity):
    """Base class for Smart Heating sensors."""

    def __init__(self, coordinator: SmartHeatingCoordinator, zone: str, key: str) -> None:
        super().__init__(coordinator)
        self._zone = zone
        self._key = key
        self._attr_unique_id = f"smart_heating_{zone}_{key}"
        self._attr_has_entity_name = True

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"smart_heating_{self._zone}")},
            "name": f"Smart Heating {self._zone.title()}",
            "manufacturer": "Smart Heating",
            "model": "Anticipation intelligente",
            "sw_version": "0.1.0",
        }


class SmartHeatingStateSensor(SmartHeatingSensorBase):
    """Zone state sensor (learning/ready/anticipating)."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "state")
        self._attr_name = "État"
        self._attr_icon = "mdi:brain"

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data:
            return self.coordinator.data.get("state")
        return None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            "zone": self._zone,
            "hvac_action": data.get("hvac_action"),
            "llm_provider": data.get("llm_provider"),
            "llm_model": data.get("llm_model"),
        }


class SmartHeatingSessionsSensor(SmartHeatingSensorBase):
    """Number of collected sessions."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "sessions")
        self._attr_name = "Sessions"
        self._attr_icon = "mdi:database"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data:
            return self.coordinator.data.get("num_sessions", 0)
        return 0


class SmartHeatingMinPerDegSensor(SmartHeatingSensorBase):
    """Minutes per degree sensor."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "min_per_deg")
        self._attr_name = "Minutes par °C"
        self._attr_icon = "mdi:timer-outline"
        self._attr_native_unit_of_measurement = "min"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data:
            return self.coordinator.data.get("min_per_deg")
        return None


class SmartHeatingSpeedSensor(SmartHeatingSensorBase):
    """Heating speed sensor."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "speed")
        self._attr_name = "Vitesse montée"
        self._attr_icon = "mdi:trending-up"
        self._attr_native_unit_of_measurement = "°C/min"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data:
            speed = self.coordinator.data.get("avg_speed")
            if speed:
                return round(speed, 4)
        return None


class SmartHeatingAnticipationSensor(SmartHeatingSensorBase):
    """Anticipation info sensor."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "anticipation")
        self._attr_name = "Anticipation"
        self._attr_icon = "mdi:clock-fast"
        self._attr_native_unit_of_measurement = "min"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data or {}
        anticipation = data.get("anticipation", {})
        return anticipation.get("minutes_needed")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        anticipation = data.get("anticipation", {})
        schedule = data.get("schedule", {})
        return {
            "active": data.get("anticipation_active", False),
            "next_consigne": anticipation.get("next_consigne"),
            "optimal_start": anticipation.get("optimal_start"),
            "should_start_now": anticipation.get("should_start_now"),
            "minutes_until_start": anticipation.get("minutes_until_start"),
            "next_transition_time": schedule.get("next_transition_time"),
            "next_transition_temp": schedule.get("next_transition_temp"),
            "effective_margin": data.get("effective_margin"),
        }


class SmartHeatingLLMAdviceSensor(SmartHeatingSensorBase):
    """LLM advice sensor."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "llm_advice")
        self._attr_name = "Conseil IA"
        self._attr_icon = "mdi:robot"

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data or {}
        reasoning = data.get("llm_reasoning", "")
        return reasoning if reasoning else "Aucun conseil"

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            "provider": data.get("llm_provider"),
            "model": data.get("llm_model"),
            "margin_adjustment": data.get("llm_margin_adjustment", 0),
            "last_update": data.get("llm_last_update"),
        }


class SmartHeatingEffectiveMarginSensor(SmartHeatingSensorBase):
    """Effective margin sensor (base + LLM + feedback)."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "effective_margin")
        self._attr_name = "Marge effective"
        self._attr_icon = "mdi:shield-check"
        self._attr_native_unit_of_measurement = "%"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data or {}
        margin = data.get("effective_margin")
        if margin is not None:
            return round(margin * 100)
        return None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            "base_margin": round(data.get("safety_margin", 0) * 100) if data.get("safety_margin") else None,
            "llm_adjustment": round(data.get("llm_margin_adjustment", 0) * 100),
            "feedback_adjustment": round(data.get("feedback_adjustment", 0) * 100),
        }


class SmartHeatingScheduleSensor(SmartHeatingSensorBase):
    """Schedule info sensor - shows next transition."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "schedule")
        self._attr_name = "Prochain créneau"
        self._attr_icon = "mdi:calendar-clock"

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data or {}
        schedule = data.get("schedule", {})
        next_time = schedule.get("next_transition_time")
        next_temp = schedule.get("next_transition_temp")
        if next_time and next_temp:
            return f"{next_temp}°C à {next_time}"
        return "Aucun"

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return data.get("schedule", {})


class SmartHeatingFeedbackSensor(SmartHeatingSensorBase):
    """Feedback stats sensor - shows anticipation accuracy."""

    def __init__(self, coordinator, zone):
        super().__init__(coordinator, zone, "feedback")
        self._attr_name = "Performance"
        self._attr_icon = "mdi:chart-line"

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data or {}
        stats = data.get("feedback_stats", {})
        rate = stats.get("success_rate")
        if rate is not None:
            return f"{rate:.0f}%"
        return "N/A"

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return data.get("feedback_stats", {})
