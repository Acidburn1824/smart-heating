"""DataUpdateCoordinator for Smart Heating."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
    async_track_time_change,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
    DOMAIN,
    CONF_ZONE_NAME,
    CONF_SENSOR_TEMP,
    CONF_SENSOR_EXT,
    CONF_CLIMATE_ENTITY,
    CONF_SCHEDULE_ENTITY,
    CONF_WEATHER_ENTITY,
    CONF_SAFETY_MARGIN,
    CONF_WARMUP_IGNORE_MIN,
    CONF_ANTI_SHORT_CYCLE,
    CONF_MIN_OFF_TIME_SEC,
    CONF_MIN_SESSIONS,
    CONF_LLM_PROVIDER,
    CONF_LLM_API_KEY,
    CONF_LLM_MODEL,
    CONF_LLM_URL,
    DEFAULT_SAFETY_MARGIN,
    DEFAULT_WARMUP_IGNORE_MIN,
    DEFAULT_MIN_OFF_TIME_SEC,
    DEFAULT_MIN_SESSIONS,
    LLM_NONE,
    MIN_SESSION_DURATION_SEC,
    MIN_SESSION_DELTA_TEMP,
    STATE_LEARNING,
    STATE_READY,
    STATE_ANTICIPATING,
    STATE_IDLE,
    MAX_SESSIONS,
)
from .thermal_model import ThermalModel, HeatingSession
from .anticipation import AnticipationEngine
from .schedule_parser import ScheduleParser
from .feedback import FeedbackLoop
from .llm import create_provider, LLMResponse

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=2)


class SmartHeatingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for a single heating zone."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        self.entry = entry
        self.config = entry.data
        self.zone_name: str = self.config.get(CONF_ZONE_NAME, "zone")

        super().__init__(
            hass,
            _LOGGER,
            name=f"smart_heating_{self.zone_name}",
            update_interval=SCAN_INTERVAL,
        )

        # Config values
        self.sensor_temp: str = self.config[CONF_SENSOR_TEMP]
        self.sensor_ext: str = self.config[CONF_SENSOR_EXT]
        self.climate_entity: str = self.config[CONF_CLIMATE_ENTITY]
        self.schedule_entity: str | None = self.config.get(CONF_SCHEDULE_ENTITY)
        self.weather_entity: str | None = self.config.get(CONF_WEATHER_ENTITY)
        margin_pct = self.config.get(CONF_SAFETY_MARGIN, int(DEFAULT_SAFETY_MARGIN * 100))
        self.safety_margin: float = margin_pct / 100.0
        self.warmup_ignore_min: float = self.config.get(CONF_WARMUP_IGNORE_MIN, DEFAULT_WARMUP_IGNORE_MIN)
        self.anti_short_cycle: bool = self.config.get(CONF_ANTI_SHORT_CYCLE, False)
        self.min_off_time_sec: int = self.config.get(CONF_MIN_OFF_TIME_SEC, DEFAULT_MIN_OFF_TIME_SEC // 60) * 60
        self.min_sessions: int = self.config.get(CONF_MIN_SESSIONS, DEFAULT_MIN_SESSIONS)

        # Thermal model
        self.thermal_model = ThermalModel(warmup_ignore_min=self.warmup_ignore_min)

        # LLM provider
        provider_type = self.config.get(CONF_LLM_PROVIDER, LLM_NONE)
        llm_config = {
            "api_key": self.config.get(CONF_LLM_API_KEY, ""),
            "model": self.config.get(CONF_LLM_MODEL, ""),
            "url": self.config.get(CONF_LLM_URL, ""),
            "agent_id": self.config.get("agent_id", ""),
        }
        self.llm_provider = create_provider(provider_type, llm_config, hass)

        # State
        self._current_session: dict[str, Any] | None = None
        self._last_off_time: datetime | None = None
        self._anticipation_active: bool = False
        self._last_llm_response: LLMResponse | None = None
        self._llm_margin_adjustment: float = 0.0
        self._unsub_listeners: list[Any] = []

        # Switches
        self.enabled: bool = True
        self.llm_enabled: bool = True

        # Anticipation engine
        self.anticipation = AnticipationEngine(
            hass=hass,
            zone_name=self.zone_name,
            climate_entity=self.climate_entity,
            schedule_entity=self.schedule_entity,
            anti_short_cycle=self.anti_short_cycle,
            min_off_time_sec=self.min_off_time_sec,
        )

        # Schedule parser
        self.schedule_parser = ScheduleParser(hass, self.schedule_entity)

        # Feedback loop
        self.feedback = FeedbackLoop(self.zone_name)

        # Storage path
        self._storage_path = Path(hass.config.path(f".storage/smart_heating_{self.zone_name}.json"))

        # Load persisted data
        self._load_data()

    def _load_data(self) -> None:
        """Load persisted sessions and state."""
        try:
            if self._storage_path.exists():
                data = json.loads(self._storage_path.read_text())
                self.thermal_model.load_sessions(data.get("sessions", []))
                self._last_off_time_str = data.get("last_off_time")
                if self._last_off_time_str:
                    self._last_off_time = datetime.fromisoformat(self._last_off_time_str)
                llm_data = data.get("last_llm_response")
                if llm_data:
                    self._llm_margin_adjustment = llm_data.get("margin_adjustment", 0)
                self.feedback.load_history(data.get("feedback_history", []))
                _LOGGER.info(
                    "Smart Heating [%s] : %d sessions chargées",
                    self.zone_name,
                    self.thermal_model.num_sessions,
                )
        except Exception as e:
            _LOGGER.error("Error loading data for %s: %s", self.zone_name, e)

    def _save_data(self) -> None:
        """Persist sessions and state."""
        try:
            data = {
                "sessions": self.thermal_model.get_sessions_data(),
                "last_off_time": self._last_off_time.isoformat() if self._last_off_time else None,
                "last_llm_response": {
                    "margin_adjustment": self._llm_margin_adjustment,
                    "reasoning": self._last_llm_response.reasoning if self._last_llm_response else "",
                    "timestamp": self._last_llm_response.timestamp if self._last_llm_response else "",
                    "provider": self._last_llm_response.provider if self._last_llm_response else "",
                },
                "feedback_history": self.feedback.get_history_data(),
            }
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._storage_path.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            _LOGGER.error("Error saving data for %s: %s", self.zone_name, e)

    # =============================================
    #  SETUP & LISTENERS
    # =============================================

    async def _async_update_data(self) -> dict[str, Any]:
        """Periodic update - check anticipation & collect data."""
        if not self.enabled:
            return {
                "zone_name": self.zone_name,
                "state": "disabled",
                "enabled": False,
            }

        temp_indoor = self._get_float_state(self.sensor_temp)
        temp_outdoor = self._get_float_state(self.sensor_ext)
        hvac_action = self._get_attribute(self.climate_entity, "hvac_action")
        current_setpoint = self._get_attribute(self.climate_entity, "temperature")

        # Track sessions
        self._track_heating_session(hvac_action, temp_indoor, temp_outdoor)

        # --- SCHEDULE PARSER: find next heating transition ---
        next_transition = self.schedule_parser.get_next_heating_transition()

        # --- CALCULATE ANTICIPATION with schedule-aware timing ---
        anticipation_calc = self._calculate_anticipation(
            temp_indoor, temp_outdoor, next_transition
        )

        # --- FEEDBACK: apply auto-calibration to margin ---
        feedback_adjustment = self.feedback.get_margin_suggestion() or 0.0

        # Effective margin = base + LLM + feedback
        effective_margin = self.safety_margin + self._llm_margin_adjustment + feedback_adjustment

        # --- ANTICIPATION ENGINE: decide & act ---
        target_time_dt = None
        if next_transition and next_transition.target_time:
            target_time_dt = next_transition.target_time

        anticipation_state = await self.anticipation.async_evaluate(
            temp_indoor=temp_indoor,
            temp_outdoor=temp_outdoor,
            minutes_needed=anticipation_calc.get("minutes_needed"),
            next_consigne=anticipation_calc.get("next_consigne"),
            is_anti_cycle_active=self._is_anti_cycle_active(),
            target_time=target_time_dt,
            effective_margin=effective_margin,
        )

        # --- FEEDBACK: track start & result ---
        was_active = self._anticipation_active
        self._anticipation_active = anticipation_state.active

        # Anticipation just started — begin feedback tracking
        if not was_active and anticipation_state.active and temp_indoor is not None:
            self.feedback.start_tracking(
                target_temp=anticipation_state.target_consigne or 0,
                target_time=anticipation_state.target_time or datetime.now(),
                temp_at_start=temp_indoor,
                margin_used=effective_margin,
                llm_adjustment=self._llm_margin_adjustment,
                ext_temp=temp_outdoor or 0,
            )

        # Anticipation just ended — record result
        if was_active and not anticipation_state.active and temp_indoor is not None:
            result = self.feedback.record_result(
                current_temp=temp_indoor,
                reached_target=(
                    anticipation_calc.get("next_consigne") is not None
                    and temp_indoor >= anticipation_calc["next_consigne"] - 0.3
                ),
            )
            if result:
                self._save_data()

        # Build state
        state = self._compute_state()

        # Schedule info for display
        schedule_info = {}
        if next_transition:
            schedule_info = {
                "next_transition_time": (
                    next_transition.target_time.strftime("%H:%M")
                    if next_transition.target_time else None
                ),
                "next_transition_temp": next_transition.target_temp,
                "current_schedule_temp": next_transition.current_temp_schedule,
                "minutes_until_transition": (
                    round(next_transition.minutes_until, 0)
                    if next_transition.minutes_until is not None else None
                ),
                "schedule_source": next_transition.source,
            }

        return {
            "zone_name": self.zone_name,
            "state": state,
            "enabled": self.enabled,
            "temp_indoor": temp_indoor,
            "temp_outdoor": temp_outdoor,
            "hvac_action": hvac_action,
            "current_setpoint": current_setpoint,
            "num_sessions": self.thermal_model.num_sessions,
            "min_per_deg": self.thermal_model.min_per_deg,
            "avg_speed": self.thermal_model.avg_speed,
            "anticipation_active": anticipation_state.active,
            "anticipation": {
                **anticipation_calc,
                **self.anticipation.to_dict(),
            },
            "schedule": schedule_info,
            "safety_margin": self.safety_margin,
            "effective_margin": effective_margin,
            "feedback_adjustment": feedback_adjustment,
            "feedback_stats": self.feedback.stats,
            "llm_provider": self.llm_provider.name,
            "llm_model": self.llm_provider.model,
            "llm_margin_adjustment": self._llm_margin_adjustment,
            "llm_reasoning": self._last_llm_response.reasoning if self._last_llm_response else "",
            "llm_last_update": self._last_llm_response.timestamp if self._last_llm_response else "",
            "anti_cycle_active": self._is_anti_cycle_active(),
        }

    async def async_setup(self) -> None:
        """Set up listeners after first refresh."""
        # Listen to hvac_action changes for session tracking
        self._unsub_listeners.append(
            async_track_state_change_event(
                self.hass, [self.climate_entity], self._on_climate_change
            )
        )

        # Listen to schedule changes for anticipation
        if self.schedule_entity:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self.hass, [self.schedule_entity], self._on_schedule_change
                )
            )

        # LLM calls at 9h and 16h
        self._unsub_listeners.append(
            async_track_time_change(self.hass, self._on_llm_morning, hour=9, minute=0, second=0)
        )
        self._unsub_listeners.append(
            async_track_time_change(self.hass, self._on_llm_evening, hour=16, minute=0, second=0)
        )

        # Register services
        self.hass.services.async_register(
            DOMAIN, "force_llm_call", self._handle_force_llm_call
        )
        self.hass.services.async_register(
            DOMAIN, "reset_sessions", self._handle_reset_sessions
        )
        self.hass.services.async_register(
            DOMAIN, "recalculate", self._handle_recalculate
        )

    @callback
    def async_shutdown(self) -> None:
        """Clean up listeners."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()
        self._save_data()

    # =============================================
    #  HELPERS
    # =============================================

    def _get_float_state(self, entity_id: str) -> float | None:
        """Get float state value."""
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def _get_attribute(self, entity_id: str, attr: str) -> Any:
        """Get entity attribute."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        return state.attributes.get(attr)

    def _get_schedule_consigne(self) -> float | None:
        """Get current schedule setpoint."""
        if not self.schedule_entity:
            return None
        return self._get_float_state(self.schedule_entity)

    def _get_weather_forecast(self) -> dict[str, Any]:
        """Get weather forecast data."""
        if not self.weather_entity:
            return {}
        state = self.hass.states.get(self.weather_entity)
        if state is None:
            return {}
        return {
            "current": state.state,
            "temperature": state.attributes.get("temperature"),
            "forecast": state.attributes.get("forecast", []),
        }

    # =============================================
    #  SESSION TRACKING
    # =============================================

    def _track_heating_session(
        self, hvac_action: str | None, temp_indoor: float | None, temp_outdoor: float | None
    ) -> None:
        """Track heating sessions for learning."""
        if hvac_action == "heating" and self._current_session is None:
            # Start session
            if temp_indoor is not None:
                self._current_session = {
                    "start_time": datetime.now(),
                    "temp_start": temp_indoor,
                    "temp_ext_start": temp_outdoor,
                    "points": [{"time": datetime.now().isoformat(), "temp": temp_indoor}],
                }
                _LOGGER.debug("[%s] Session started at %.1f°C", self.zone_name, temp_indoor)

        elif hvac_action == "heating" and self._current_session is not None:
            # Continue session - add point
            if temp_indoor is not None:
                self._current_session["points"].append(
                    {"time": datetime.now().isoformat(), "temp": temp_indoor}
                )

        elif hvac_action != "heating" and self._current_session is not None:
            # End session
            self._end_session(temp_indoor, temp_outdoor)

    def _end_session(self, temp_indoor: float | None, temp_outdoor: float | None) -> None:
        """End current session and record it."""
        if self._current_session is None or temp_indoor is None:
            self._current_session = None
            return

        session = self._current_session
        self._current_session = None
        self._last_off_time = datetime.now()

        duration = (datetime.now() - session["start_time"]).total_seconds()
        delta_temp = temp_indoor - session["temp_start"]

        # Filter: minimum duration and delta
        if duration < MIN_SESSION_DURATION_SEC or delta_temp < MIN_SESSION_DELTA_TEMP:
            _LOGGER.debug(
                "[%s] Session trop courte ignorée (%.0fs, %.1f°C)",
                self.zone_name, duration, delta_temp,
            )
            return

        duration_min = duration / 60.0

        # Ignore warmup period for speed calculation
        effective_duration = max(0, duration_min - self.warmup_ignore_min)
        if effective_duration <= 0:
            return

        speed = delta_temp / effective_duration

        # Average ext temp
        ext_temps = []
        if session.get("temp_ext_start") is not None:
            ext_temps.append(session["temp_ext_start"])
        if temp_outdoor is not None:
            ext_temps.append(temp_outdoor)
        temp_ext_avg = sum(ext_temps) / len(ext_temps) if ext_temps else 0

        heating_session = HeatingSession(
            date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            temp_start=session["temp_start"],
            temp_end=temp_indoor,
            temp_ext_avg=round(temp_ext_avg, 1),
            delta_temp=round(delta_temp, 2),
            duration_min=round(duration_min, 1),
            speed_degc_per_min=round(speed, 5),
            anticipated=self._anticipation_active,
        )

        self.thermal_model.add_session(heating_session)
        self._save_data()

        _LOGGER.info(
            "[%s] Session enregistrée : %.1f->%.1f°C en %.0fmin (%.4f°C/min)",
            self.zone_name,
            heating_session.temp_start,
            heating_session.temp_end,
            heating_session.duration_min,
            heating_session.speed_degc_per_min,
        )

    # =============================================
    #  ANTICIPATION
    # =============================================

    def _calculate_anticipation(
        self,
        temp_indoor: float | None,
        temp_outdoor: float | None,
        next_transition=None,
    ) -> dict[str, Any]:
        """Calculate anticipation timing using schedule parser.

        Args:
            temp_indoor: Current indoor temperature
            temp_outdoor: Current outdoor temperature
            next_transition: NextTransition from schedule_parser (or None)
        """
        result = {
            "optimal_start": None,
            "minutes_needed": None,
            "next_consigne": None,
            "next_time": None,
        }

        if temp_indoor is None or temp_outdoor is None:
            return result

        # Need enough sessions to calculate
        if self.thermal_model.num_sessions < self.min_sessions:
            return result

        # --- Determine target from schedule parser ---
        next_consigne = None
        target_time = None

        if next_transition and next_transition.is_heating_up:
            next_consigne = next_transition.target_temp
            target_time = next_transition.target_time
        else:
            # Fallback: simple consigne comparison
            schedule_consigne = self._get_schedule_consigne()
            if schedule_consigne is not None and schedule_consigne > temp_indoor + 0.3:
                next_consigne = schedule_consigne

        if next_consigne is None or next_consigne <= temp_indoor:
            return result

        # --- Effective margin (base + LLM + feedback) ---
        feedback_adj = self.feedback.get_margin_suggestion() or 0.0
        effective_margin = self.safety_margin + self._llm_margin_adjustment + feedback_adj

        # --- Estimate time needed ---
        minutes_needed = self.thermal_model.estimate_time_to_target(
            current_temp=temp_indoor,
            target_temp=next_consigne,
            ext_temp=temp_outdoor,
            margin=effective_margin,
        )

        if minutes_needed is None:
            return result

        result["minutes_needed"] = minutes_needed
        result["next_consigne"] = next_consigne

        # --- Calculate optimal start time ---
        if target_time is not None:
            from datetime import timedelta
            optimal_start = target_time - timedelta(minutes=minutes_needed)
            result["next_time"] = target_time.isoformat()
            result["optimal_start"] = optimal_start.isoformat()

            minutes_until_transition = next_transition.minutes_until
            if minutes_until_transition is not None:
                result["should_start_now"] = minutes_until_transition <= minutes_needed
                result["minutes_until_start"] = round(
                    minutes_until_transition - minutes_needed, 0
                )
            else:
                result["should_start_now"] = True
                result["minutes_until_start"] = 0
        else:
            # No target_time known — start immediately if delta > 0
            result["should_start_now"] = True
            result["minutes_until_start"] = 0

        return result

    def _compute_state(self) -> str:
        """Compute overall state."""
        if self.thermal_model.num_sessions < self.min_sessions:
            return STATE_LEARNING
        if self._anticipation_active:
            return STATE_ANTICIPATING
        return STATE_READY

    def _is_anti_cycle_active(self) -> bool:
        """Check if anti-cycle is preventing restart."""
        if not self.anti_short_cycle or self._last_off_time is None:
            return False
        elapsed = (datetime.now() - self._last_off_time).total_seconds()
        return elapsed < self.min_off_time_sec

    # =============================================
    #  EVENT HANDLERS
    # =============================================

    @callback
    def _on_climate_change(self, event: Event) -> None:
        """Handle climate entity state changes."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None or old_state is None:
            return

        new_action = new_state.attributes.get("hvac_action")
        old_action = old_state.attributes.get("hvac_action")

        if old_action != new_action:
            _LOGGER.debug(
                "[%s] hvac_action changed: %s -> %s",
                self.zone_name, old_action, new_action,
            )
            # Force refresh to track session
            self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _on_schedule_change(self, event: Event) -> None:
        """Handle schedule entity state changes - trigger anticipation check."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None or old_state is None:
            return

        try:
            new_val = float(new_state.state)
            old_val = float(old_state.state)
        except (ValueError, TypeError):
            return

        if abs(new_val - old_val) > 0.1:
            _LOGGER.info(
                "[%s] 📅 Schedule changé : %.1f → %.1f°C",
                self.zone_name, old_val, new_val,
            )
            # If temp dropped (transition to eco), deactivate anticipation
            if new_val < old_val and self.anticipation.state.active:
                _LOGGER.info(
                    "[%s] Transition vers éco, désactivation anticipation",
                    self.zone_name,
                )
                self.anticipation._deactivate()

            # Force refresh to re-evaluate
            self.hass.async_create_task(self.async_request_refresh())

    async def _on_llm_morning(self, _now: datetime) -> None:
        """Morning LLM call."""
        await self._call_llm("morning")

    async def _on_llm_evening(self, _now: datetime) -> None:
        """Evening LLM call."""
        await self._call_llm("evening")

    async def _call_llm(self, context: str) -> None:
        """Call LLM provider for margin adjustment."""
        if not self.llm_enabled:
            _LOGGER.debug("[%s] LLM disabled, skipping", self.zone_name)
            return

        if self.llm_provider.name == "None":
            # Still call for algorithmic adjustment
            pass

        _LOGGER.info("[%s] Appel LLM (%s) - contexte: %s", self.zone_name, self.llm_provider.name, context)

        temp_indoor = self._get_float_state(self.sensor_temp)
        temp_outdoor = self._get_float_state(self.sensor_ext)

        thermal_data = self.thermal_model.inertia_data
        thermal_data["recent_sessions"] = self.thermal_model.get_sessions_data()[-10:]

        weather_forecast = self._get_weather_forecast()

        current_state = {
            "temp_indoor": temp_indoor,
            "temp_outdoor": temp_outdoor,
            "setpoint": self._get_schedule_consigne(),
            "margin": int(self.safety_margin * 100),
        }

        try:
            response = await self.llm_provider.async_get_adjustment(
                zone_name=self.zone_name,
                thermal_data=thermal_data,
                weather_forecast=weather_forecast,
                current_state=current_state,
                context=context,
            )

            if response.error:
                _LOGGER.error("[%s] LLM error: %s", self.zone_name, response.error)
            else:
                self._last_llm_response = response
                self._llm_margin_adjustment = response.margin_adjustment
                _LOGGER.info(
                    "[%s] LLM [%s] : marge %+.0f%% | %s",
                    self.zone_name,
                    context,
                    response.margin_adjustment * 100,
                    response.reasoning,
                )
                self._save_data()
                await self.async_request_refresh()

        except Exception as e:
            _LOGGER.error("[%s] LLM call failed: %s", self.zone_name, e)

    # =============================================
    #  SERVICE HANDLERS
    # =============================================

    async def _handle_force_llm_call(self, call) -> None:
        """Handle force_llm_call service."""
        context = call.data.get("context", "morning")
        await self._call_llm(context)

    async def _handle_reset_sessions(self, call) -> None:
        """Handle reset_sessions service."""
        _LOGGER.info("[%s] Resetting all sessions", self.zone_name)
        self.thermal_model.sessions.clear()
        self.thermal_model._recalculate()
        self._save_data()
        await self.async_request_refresh()

    async def _handle_recalculate(self, call) -> None:
        """Handle recalculate service."""
        _LOGGER.info("[%s] Forcing recalculation", self.zone_name)
        await self.async_request_refresh()
