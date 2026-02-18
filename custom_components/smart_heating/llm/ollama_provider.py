"""Ollama LLM provider for Smart Heating (local AI)."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .base import LLMProvider, LLMResponse

_LOGGER = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama provider for local LLM (Llama3, Mistral, etc.)."""

    @property
    def name(self) -> str:
        return "Ollama"

    @property
    def model(self) -> str:
        return self._config.get("model", "llama3")

    @property
    def url(self) -> str:
        return self._config.get("url", "http://localhost:11434")

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

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "system": "Tu es un assistant expert en chauffage intelligent. Réponds uniquement en JSON.",
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 200,
                        },
                    },
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        return LLMResponse(
                            error=f"Ollama HTTP {resp.status}: {error_text}",
                            provider=self.name,
                            model=self.model,
                        )
                    data = await resp.json()
                    raw = data.get("response", "")

            _LOGGER.debug("Ollama response for %s: %s", zone_name, raw)
            return self._parse_response(raw, self.name, self.model)

        except aiohttp.ClientError as e:
            _LOGGER.error("Ollama connection error for %s: %s", zone_name, e)
            return LLMResponse(
                error=f"Connection error: {e}",
                provider=self.name,
                model=self.model,
            )
        except Exception as e:
            _LOGGER.error("Ollama error for %s: %s", zone_name, e)
            return LLMResponse(error=str(e), provider=self.name, model=self.model)
