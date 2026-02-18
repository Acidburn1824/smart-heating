"""Home Assistant Conversation LLM provider for Smart Heating."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.components.conversation import async_converse

from .base import LLMProvider, LLMResponse

_LOGGER = logging.getLogger(__name__)


class HAConversationProvider(LLMProvider):
    """Use HA's built-in Conversation integration as LLM provider."""

    def __init__(self, config: dict[str, Any], hass: HomeAssistant) -> None:
        super().__init__(config)
        self._hass = hass

    @property
    def name(self) -> str:
        return "HA Conversation"

    @property
    def model(self) -> str:
        return self._config.get("agent_id", "default")

    async def async_get_adjustment(
        self,
        zone_name: str,
        thermal_data: dict[str, Any],
        weather_forecast: dict[str, Any],
        current_state: dict[str, Any],
        context: str,
    ) -> LLMResponse:
        try:
            prompt = self._build_prompt(
                zone_name, thermal_data, weather_forecast, current_state, context
            )

            agent_id = self._config.get("agent_id")
            result = await async_converse(
                hass=self._hass,
                text=prompt,
                conversation_id=f"smart_heating_{zone_name}",
                context=self._hass.data.get("context"),
                agent_id=agent_id,
            )

            raw = result.response.speech.get("plain", {}).get("speech", "")
            _LOGGER.debug("HA Conversation response for %s: %s", zone_name, raw)
            return self._parse_response(raw, self.name, agent_id or "default")

        except Exception as e:
            _LOGGER.error("HA Conversation error for %s: %s", zone_name, e)
            return LLMResponse(error=str(e), provider=self.name, model=self.model)
