"""Diagnostics for Smart Heating."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_LLM_API_KEY
from .coordinator import SmartHeatingCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: SmartHeatingCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Mask sensitive data
    config = dict(entry.data)
    if CONF_LLM_API_KEY in config:
        key = config[CONF_LLM_API_KEY]
        config[CONF_LLM_API_KEY] = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"

    data = coordinator.data or {}

    return {
        "config": config,
        "state": {
            "zone_name": coordinator.zone_name,
            "enabled": coordinator.enabled,
            "llm_enabled": coordinator.llm_enabled,
            "safety_margin": coordinator.safety_margin,
            "warmup_ignore_min": coordinator.warmup_ignore_min,
            "anti_short_cycle": coordinator.anti_short_cycle,
            "min_sessions": coordinator.min_sessions,
        },
        "thermal_model": {
            "num_sessions": coordinator.thermal_model.num_sessions,
            "avg_speed": coordinator.thermal_model.avg_speed,
            "min_per_deg": coordinator.thermal_model.min_per_deg,
            "inertia": coordinator.thermal_model.inertia_data,
            "last_5_sessions": coordinator.thermal_model.get_sessions_data()[-5:],
        },
        "anticipation": coordinator.anticipation.to_dict(),
        "schedule": {
            "next_transition": (
                {
                    "target_time": t.target_time.isoformat() if t.target_time else None,
                    "target_temp": t.target_temp,
                    "current_temp_schedule": t.current_temp_schedule,
                    "is_heating_up": t.is_heating_up,
                    "source": t.source,
                }
                if (t := coordinator.schedule_parser.get_next_heating_transition())
                else None
            ),
        },
        "feedback": coordinator.feedback.stats,
        "llm": {
            "provider": coordinator.llm_provider.name,
            "model": coordinator.llm_provider.model,
            "margin_adjustment": coordinator._llm_margin_adjustment,
            "last_reasoning": (
                coordinator._last_llm_response.reasoning
                if coordinator._last_llm_response
                else None
            ),
            "last_timestamp": (
                coordinator._last_llm_response.timestamp
                if coordinator._last_llm_response
                else None
            ),
        },
        "current_data": {
            "temp_indoor": data.get("temp_indoor"),
            "temp_outdoor": data.get("temp_outdoor"),
            "hvac_action": data.get("hvac_action"),
            "current_setpoint": data.get("current_setpoint"),
            "effective_margin": data.get("effective_margin"),
        },
    }
