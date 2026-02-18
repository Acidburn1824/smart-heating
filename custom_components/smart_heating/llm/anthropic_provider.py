"""Anthropic LLM provider for Smart Heating."""
from __future__ import annotations

import logging
from typing import Any

from .base import LLMProvider, LLMResponse

_LOGGER = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Anthropic provider (Claude Sonnet, Opus, Haiku)."""

    @property
    def name(self) -> str:
        return "Anthropic"

    @property
    def model(self) -> str:
        return self._config.get("model", "claude-sonnet-4-5-20250514")

    async def async_get_adjustment(
        self,
        zone_name: str,
        thermal_data: dict[str, Any],
        weather_forecast: dict[str, Any],
        current_state: dict[str, Any],
        context: str,
    ) -> LLMResponse:
        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=self._config["api_key"])
            prompt = self._build_prompt(
                zone_name, thermal_data, weather_forecast, current_state, context
            )

            response = await client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
                system="Tu es un assistant expert en chauffage intelligent. Réponds uniquement en JSON.",
            )

            raw = response.content[0].text if response.content else ""
            _LOGGER.debug("Anthropic response for %s: %s", zone_name, raw)
            return self._parse_response(raw, self.name, self.model)

        except ImportError:
            return LLMResponse(error="anthropic package not installed", provider=self.name, model=self.model)
        except Exception as e:
            _LOGGER.error("Anthropic API error for %s: %s", zone_name, e)
            return LLMResponse(error=str(e), provider=self.name, model=self.model)
