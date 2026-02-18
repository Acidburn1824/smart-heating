"""Anticipation engine - actively controls climate entities for optimal start times.

This module monitors schedule transitions and sends early setpoint changes
to the climate entity so the room reaches target temperature on time.

Flow:
1. Every 2 min, check if the NEXT schedule transition requires heating up
2. Calculate how many minutes are needed based on thermal model
3. If it's time to start → send target consigne to climate entity
4. Track if we arrived on time for continuous improvement
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

_LOGGER = logging.getLogger(__name__)


@dataclass
class ScheduleTransition:
    """A detected upcoming schedule transition."""

    target_time: datetime  # When the transition happens
    target_temp: float  # Target temperature after transition
    current_temp: float  # Current indoor temperature
    current_consigne: float  # Current schedule consigne
    delta_temp: float  # How much we need to heat

    @property
    def is_heating_needed(self) -> bool:
        """Does this transition require heating up?"""
        return self.delta_temp > 0.3


@dataclass
class AnticipationState:
    """Current state of the anticipation engine."""

    active: bool = False
    target_consigne: float | None = None
    target_time: datetime | None = None
    minutes_needed: float | None = None
    minutes_until_target: float | None = None
    optimal_start_time: datetime | None = None
    started_at: datetime | None = None
    temp_at_start: float | None = None


class AnticipationEngine:
    """Actively monitors schedule and sends anticipation commands."""

    def __init__(
        self,
        hass: HomeAssistant,
        zone_name: str,
        climate_entity: str,
        schedule_entity: str | None,
        anti_short_cycle: bool = False,
        min_off_time_sec: int = 1800,
    ) -> None:
        self.hass = hass
        self.zone_name = zone_name
        self.climate_entity = climate_entity
        self.schedule_entity = schedule_entity
        self.anti_short_cycle = anti_short_cycle
        self.min_off_time_sec = min_off_time_sec

        self.state = AnticipationState()
        self._last_consigne_sent: float | None = None
        self._last_consigne_sent_time: datetime | None = None

    async def async_evaluate(
        self,
        temp_indoor: float | None,
        temp_outdoor: float | None,
        minutes_needed: float | None,
        next_consigne: float | None,
        is_anti_cycle_active: bool,
        target_time: datetime | None = None,
        effective_margin: float = 1.15,
    ) -> AnticipationState:
        """Evaluate and act on anticipation.

        Called every 2 minutes by the coordinator.
        Returns updated AnticipationState.

        Args:
            temp_indoor: Current indoor temperature
            temp_outdoor: Current outdoor temperature  
            minutes_needed: Estimated minutes to reach target (from thermal model)
            next_consigne: Next schedule target temperature
            is_anti_cycle_active: Whether anti-cycle is preventing restart
            target_time: When the schedule transition happens (from schedule_parser)
            effective_margin: Combined margin (base + LLM + feedback)
        """
        now = datetime.now()

        # --- No data or no target ---
        if temp_indoor is None or next_consigne is None or minutes_needed is None:
            if self.state.active:
                _LOGGER.debug("[%s] Anticipation: données manquantes, désactivation", self.zone_name)
                self.state.active = False
            return self.state

        # --- Already at or above target ---
        if temp_indoor >= next_consigne - 0.2:
            if self.state.active:
                arrived_early = True
                if self.state.target_time:
                    minutes_early = (self.state.target_time - now).total_seconds() / 60
                    _LOGGER.info(
                        "[%s] ✅ Température cible atteinte (%.1f°C >= %.1f°C), "
                        "%.0f min avant l'heure prévue",
                        self.zone_name,
                        temp_indoor,
                        next_consigne,
                        minutes_early,
                    )
                self._deactivate()
            return self.state

        # --- Anti-cycle active: don't start ---
        if is_anti_cycle_active and not self.state.active:
            _LOGGER.debug(
                "[%s] Anti-cycle actif, anticipation reportée", self.zone_name
            )
            return self.state

        # --- Should we start anticipation? ---
        # Strategy: if we know target_time from schedule_parser,
        # start exactly (minutes_needed) before target_time.
        # If no target_time, start immediately when delta > 0.

        should_start = False
        estimated_target_time = target_time

        if target_time is not None and minutes_needed > 0:
            # We know WHEN the transition happens
            minutes_until_transition = (target_time - now).total_seconds() / 60
            minutes_until_start = minutes_until_transition - minutes_needed

            if minutes_until_start <= 2:
                # Time to start (with 2 min buffer for scan interval)
                should_start = True
                _LOGGER.debug(
                    "[%s] Schedule-aware: transition dans %.0f min, "
                    "besoin %.0f min → démarrage dans %.0f min",
                    self.zone_name,
                    minutes_until_transition,
                    minutes_needed,
                    minutes_until_start,
                )
            elif minutes_until_transition < 0:
                # Transition already passed but we're not at temp yet
                should_start = True
        else:
            # No target_time: check if consigne > current temp
            current_sched = self._get_current_consigne()
            if (
                current_sched is not None
                and next_consigne is not None
                and next_consigne > current_sched + 0.3
            ):
                should_start = True
                estimated_target_time = now + timedelta(minutes=minutes_needed)

        if should_start and not self.state.active:
            delta = next_consigne - temp_indoor
            if delta > 0.3 and minutes_needed > 0:
                if estimated_target_time is None:
                    estimated_target_time = now + timedelta(minutes=minutes_needed)

                _LOGGER.info(
                    "[%s] 🚀 Anticipation ACTIVÉE : "
                    "%.1f°C → %.1f°C (Δ%.1f°C, besoin ~%.0f min, "
                    "cible %s)",
                    self.zone_name,
                    temp_indoor,
                    next_consigne,
                    delta,
                    minutes_needed,
                    estimated_target_time.strftime("%H:%M") if estimated_target_time else "?",
                )
                self.state = AnticipationState(
                    active=True,
                    target_consigne=next_consigne,
                    target_time=estimated_target_time,
                    minutes_needed=minutes_needed,
                    minutes_until_target=minutes_needed,
                    optimal_start_time=now,
                    started_at=now,
                    temp_at_start=temp_indoor,
                )
                # Send command
                await self._send_consigne(next_consigne)

        elif self.state.active:
            if should_start or (next_consigne and temp_indoor < next_consigne - 0.2):
                # Still active - update remaining time and resend if needed
                self.state.minutes_until_target = max(
                    0,
                    (self.state.target_time - now).total_seconds() / 60
                    if self.state.target_time
                    else 0,
                )

                # Resend consigne every 10 min to fight overrides
                should_resend = (
                    self._last_consigne_sent_time is None
                    or (now - self._last_consigne_sent_time).total_seconds() > 600
                )

                # Check if climate entity has drifted
                climate_setpoint = self._get_climate_setpoint()
                if (
                    climate_setpoint is not None
                    and self.state.target_consigne is not None
                    and abs(climate_setpoint - self.state.target_consigne) > 0.3
                ):
                    _LOGGER.warning(
                        "[%s] Consigne climate a dévié (%.1f != %.1f), re-envoi",
                        self.zone_name,
                        climate_setpoint,
                        self.state.target_consigne,
                    )
                    should_resend = True

                if should_resend and self.state.target_consigne:
                    await self._send_consigne(self.state.target_consigne)
            else:
                # Schedule transition passed or no longer needed
                _LOGGER.info(
                    "[%s] Transition schedule passée, fin anticipation",
                    self.zone_name,
                )
                self._deactivate()

        return self.state

    async def _send_consigne(self, temperature: float) -> None:
        """Send temperature setpoint to climate entity."""
        now = datetime.now()

        _LOGGER.info(
            "[%s] 📤 Envoi consigne %.1f°C à %s",
            self.zone_name,
            temperature,
            self.climate_entity,
        )

        try:
            # First try set_temperature
            await self.hass.services.async_call(
                "climate",
                "set_temperature",
                {
                    "entity_id": self.climate_entity,
                    "temperature": temperature,
                },
                blocking=True,
            )

            self._last_consigne_sent = temperature
            self._last_consigne_sent_time = now

        except Exception as e:
            _LOGGER.error(
                "[%s] Erreur envoi consigne: %s", self.zone_name, e
            )

    async def async_restore_consigne(self, temperature: float) -> None:
        """Restore consigne after anticipation ends (back to schedule)."""
        _LOGGER.info(
            "[%s] 🔄 Restauration consigne planning %.1f°C",
            self.zone_name,
            temperature,
        )
        await self._send_consigne(temperature)

    def _deactivate(self) -> None:
        """Deactivate anticipation."""
        self.state = AnticipationState(active=False)
        self._last_consigne_sent = None
        self._last_consigne_sent_time = None

    def _get_current_consigne(self) -> float | None:
        """Get current schedule consigne."""
        if not self.schedule_entity:
            return None
        state = self.hass.states.get(self.schedule_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def _get_climate_setpoint(self) -> float | None:
        """Get current climate entity setpoint."""
        state = self.hass.states.get(self.climate_entity)
        if state is None:
            return None
        temp = state.attributes.get("temperature")
        if temp is None:
            return None
        try:
            return float(temp)
        except (ValueError, TypeError):
            return None

    def to_dict(self) -> dict[str, Any]:
        """Export state for sensor attributes."""
        s = self.state
        return {
            "active": s.active,
            "target_consigne": s.target_consigne,
            "target_time": s.target_time.isoformat() if s.target_time else None,
            "minutes_needed": s.minutes_needed,
            "minutes_until_target": round(s.minutes_until_target, 0) if s.minutes_until_target else None,
            "optimal_start_time": s.optimal_start_time.isoformat() if s.optimal_start_time else None,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "temp_at_start": s.temp_at_start,
            "last_consigne_sent": self._last_consigne_sent,
        }
