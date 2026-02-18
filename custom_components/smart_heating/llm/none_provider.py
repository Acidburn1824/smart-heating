"""No-AI provider for Smart Heating (pure algorithm)."""
from __future__ import annotations

from typing import Any

from .base import LLMProvider, LLMResponse


class NoneProvider(LLMProvider):
    """No AI - pure algorithmic approach."""

    @property
    def name(self) -> str:
        return "None"

    @property
    def model(self) -> str:
        return "algorithm"

    async def async_get_adjustment(
        self,
        zone_name: str,
        thermal_data: dict[str, Any],
        weather_forecast: dict[str, Any],
        current_state: dict[str, Any],
        context: str,
    ) -> LLMResponse:
        """Pure algorithmic adjustment based on weather delta."""
        try:
            temp_ext = float(current_state.get("temp_outdoor", 10))

            # Simple heuristic based on outdoor temp
            if temp_ext < -5:
                adj = 0.10  # Very cold: +10% margin
                reason = f"Froid intense ({temp_ext}°C), marge augmentée"
            elif temp_ext < 0:
                adj = 0.05  # Cold: +5%
                reason = f"Froid ({temp_ext}°C), légère marge supplémentaire"
            elif temp_ext < 5:
                adj = 0.0  # Normal winter
                reason = "Conditions hivernales normales"
            elif temp_ext < 12:
                adj = -0.03  # Mild
                reason = f"Douceur ({temp_ext}°C), marge réduite"
            else:
                adj = -0.05  # Warm
                reason = f"Temps doux ({temp_ext}°C), marge minimale"

            # Check weather forecast for wind/rain impact
            forecast = weather_forecast.get("forecast", [])
            if forecast:
                conditions = [f.get("condition", "") for f in forecast[:4]]
                if any(c in ("snowy", "snowy-rainy") for c in conditions):
                    adj += 0.05
                    reason += " + neige prévue"
                elif any(c in ("windy", "windy-variant") for c in conditions):
                    adj += 0.03
                    reason += " + vent prévu"

            return LLMResponse(
                margin_adjustment=max(-0.15, min(0.20, adj)),
                confidence=0.6,
                reasoning=reason,
                raw_response="algorithmic",
                provider=self.name,
                model=self.model,
            )
        except Exception as e:
            return LLMResponse(error=str(e), provider=self.name, model=self.model)
