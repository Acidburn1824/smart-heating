"""OpenAI LLM provider for Smart Heating."""
from __future__ import annotations

import logging
from typing import Any

from .base import LLMProvider, LLMResponse

_LOGGER = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI provider (GPT-4o-mini, GPT-4o, etc.)."""

    @property
    def name(self) -> str:
        return "OpenAI"

    @property
    def model(self) -> str:
        return self._config.get("model", "gpt-4o-mini")

    async def async_get_adjustment(
        self,
        zone_name: str,
        thermal_data: dict[str, Any],
        weather_forecast: dict[str, Any],
        current_state: dict[str, Any],
        context: str,
    ) -> LLMResponse:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self._config["api_key"])
            prompt = self._build_prompt(
                zone_name, thermal_data, weather_forecast, current_state, context
            )

            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Tu es un assistant expert en chauffage intelligent. Réponds uniquement en JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
                temperature=0.3,
            )

            raw = response.choices[0].message.content or ""
            _LOGGER.debug("OpenAI response for %s: %s", zone_name, raw)
            return self._parse_response(raw, self.name, self.model)

        except ImportError:
            return LLMResponse(error="openai package not installed", provider=self.name, model=self.model)
        except Exception as e:
            _LOGGER.error("OpenAI API error for %s: %s", zone_name, e)
            return LLMResponse(error=str(e), provider=self.name, model=self.model)
