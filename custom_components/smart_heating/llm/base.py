"""Base class for LLM providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    margin_adjustment: float = 0.0  # ex: 0.05 = +5% de marge
    confidence: float = 0.5  # 0.0 - 1.0
    reasoning: str = ""  # explication courte pour l'utilisateur
    raw_response: str = ""  # réponse brute pour debug
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    provider: str = ""
    model: str = ""
    error: str | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the provider."""
        self._config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Return provider name."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Return model name."""

    @abstractmethod
    async def async_get_adjustment(
        self,
        zone_name: str,
        thermal_data: dict[str, Any],
        weather_forecast: dict[str, Any],
        current_state: dict[str, Any],
        context: str,
    ) -> LLMResponse:
        """Get margin adjustment from LLM.

        Args:
            zone_name: Name of the heating zone
            thermal_data: Dict with inertia data, sessions, speeds
            weather_forecast: Weather forecast data
            current_state: Current temperatures and setpoints
            context: "morning" or "evening"

        Returns:
            LLMResponse with adjustment and reasoning
        """

    def _build_prompt(
        self,
        zone_name: str,
        thermal_data: dict[str, Any],
        weather_forecast: dict[str, Any],
        current_state: dict[str, Any],
        context: str,
    ) -> str:
        """Build the prompt for the LLM. Shared across all providers."""

        sessions_text = ""
        for s in thermal_data.get("recent_sessions", [])[-10:]:
            sessions_text += (
                f"  {s.get('date', '?')} : {s.get('temp_start', '?')}"
                f"->{s.get('temp_end', '?')}°C "
                f"({s.get('delta_temp', 0):+.1f}°C en "
                f"{s.get('duration_min', 0):.0f}min) "
                f"ext:{s.get('temp_ext_avg', '?')}°C\n"
            )

        weather_text = ""
        for f in weather_forecast.get("forecast", [])[:6]:
            weather_text += (
                f"  {f.get('datetime', '?')[:16]} : {f.get('condition', '?')}, "
                f"{f.get('templow', '?')}-{f.get('temperature', '?')}°C\n"
            )

        if context == "morning":
            context_text = (
                "CONTEXTE : Analyse du matin.\n"
                "Prévois la journée complète. Sois conservateur car les conditions "
                "peuvent évoluer. Si météo proche des sessions passées : peu ou pas "
                "d'ajustement. Si froid inhabituel : augmente la marge (+5 à +15%)."
            )
        else:
            context_text = (
                "CONTEXTE : Ajustement du soir.\n"
                "Corrige finement pour CE SOIR uniquement. La météo actuelle est "
                "connue avec certitude. Ajuste la marge en conséquence."
            )

        return f"""Tu es un expert en chauffage intelligent et inertie thermique.

{context_text}

DONNÉES ZONE '{zone_name}' :
- Vitesse moyenne montée : {thermal_data.get('avg_speed', 'N/A')} °C/min
- Minutes par degré : {thermal_data.get('min_per_deg', 'N/A')} min
- Sessions collectées : {thermal_data.get('num_sessions', 0)}
- Temp intérieure : {current_state.get('temp_indoor', '?')}°C
- Temp extérieure : {current_state.get('temp_outdoor', '?')}°C
- Consigne actuelle : {current_state.get('setpoint', '?')}°C
- Marge de sécurité base : {current_state.get('margin', 15)}%

DERNIÈRES SESSIONS :
{sessions_text or 'Aucune session'}

PRÉVISIONS MÉTÉO :
{weather_text or 'Non disponibles'}

Réponds UNIQUEMENT avec un JSON (pas de markdown, pas de texte avant/après) :
{{
    "margin_adjustment": <float entre -0.15 et +0.20>,
    "confidence": <float 0.0-1.0>,
    "reasoning": "<explication courte en français, max 100 caractères>"
}}

Exemples :
- Nuit froide prévue (-5°C) : {{"margin_adjustment": 0.10, "confidence": 0.8, "reasoning": "Froid intense prévu, marge augmentée"}}
- Conditions normales : {{"margin_adjustment": 0.0, "confidence": 0.9, "reasoning": "Conditions stables, pas d'ajustement"}}
- Douceur inhabituelle : {{"margin_adjustment": -0.05, "confidence": 0.7, "reasoning": "Douceur prévue, marge réduite"}}
"""

    def _parse_response(self, raw: str, provider: str, model: str) -> LLMResponse:
        """Parse JSON response from LLM."""
        import json

        try:
            # Nettoyer markdown
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.replace("```json", "").replace("```", "").strip()

            data = json.loads(cleaned)

            return LLMResponse(
                margin_adjustment=max(-0.15, min(0.20, float(data.get("margin_adjustment", 0)))),
                confidence=max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
                reasoning=str(data.get("reasoning", ""))[:200],
                raw_response=raw,
                provider=provider,
                model=model,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return LLMResponse(
                error=f"Parse error: {e}",
                raw_response=raw,
                provider=provider,
                model=model,
            )
