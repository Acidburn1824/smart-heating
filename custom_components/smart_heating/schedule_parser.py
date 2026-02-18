"""Schedule parser - detects upcoming schedule transitions.

Supports multiple schedule sources:
1. schedule_state (HACS) - sensor with events in attributes
2. VTherm presets - reads upcoming preset changes
3. HA native schedule - reads schedule.* entities
4. Manual - uses current consigne vs target as simple delta

The goal: find the NEXT time the setpoint will INCREASE
and return (target_time, target_temp, current_temp_schedule).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, time as dt_time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

_LOGGER = logging.getLogger(__name__)


@dataclass
class NextTransition:
    """An upcoming schedule transition."""

    target_time: datetime | None  # When the change happens
    target_temp: float  # Temperature after change
    current_temp_schedule: float  # Current schedule temperature
    source: str  # Where we found it

    @property
    def is_heating_up(self) -> bool:
        """Is this a transition that requires heating?"""
        return self.target_temp > self.current_temp_schedule + 0.3

    @property
    def delta(self) -> float:
        """Temperature delta."""
        return self.target_temp - self.current_temp_schedule

    @property
    def minutes_until(self) -> float | None:
        """Minutes until this transition."""
        if self.target_time is None:
            return None
        delta = (self.target_time - datetime.now()).total_seconds() / 60
        return max(0, delta)


class ScheduleParser:
    """Parse schedule entities to find next transitions."""

    def __init__(self, hass: HomeAssistant, schedule_entity: str | None) -> None:
        self.hass = hass
        self.schedule_entity = schedule_entity

    def get_next_heating_transition(self) -> NextTransition | None:
        """Find the next transition that requires heating up.

        Returns NextTransition or None if no upcoming heating transition found.
        """
        if not self.schedule_entity:
            return None

        state = self.hass.states.get(self.schedule_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None

        try:
            current_consigne = float(state.state)
        except (ValueError, TypeError):
            return None

        # Try schedule_state events (most common for Manu's setup)
        transition = self._parse_schedule_state(state, current_consigne)
        if transition:
            return transition

        # Try VTherm-style attributes
        transition = self._parse_vtherm_attrs(state, current_consigne)
        if transition:
            return transition

        # Fallback: no transition info, return current state only
        return NextTransition(
            target_time=None,
            target_temp=current_consigne,
            current_temp_schedule=current_consigne,
            source="current_only",
        )

    def _parse_schedule_state(
        self, state: Any, current_consigne: float
    ) -> NextTransition | None:
        """Parse schedule_state HACS integration attributes.

        schedule_state stores events as attributes like:
        events:
          - start: "07:30"
            end: "17:00"
            state: "16"
          - start: "17:00"
            end: "20:45"
            state: "19.5"
        """
        attrs = state.attributes
        events = attrs.get("events")

        if not events or not isinstance(events, list):
            # Try alternative attribute names
            events = attrs.get("schedule") or attrs.get("entries")
            if not events:
                return None

        now = datetime.now()
        today = now.date()
        current_weekday = now.strftime("%A").lower()

        # Parse all events and find which one is current + next
        parsed_events = []
        for event in events:
            ev = self._parse_single_event(event, today, current_weekday)
            if ev:
                parsed_events.append(ev)

        if not parsed_events:
            return None

        # Sort by start time
        parsed_events.sort(key=lambda e: e["start_dt"])

        # Find current event and next event
        current_event = None
        next_event = None

        for i, ev in enumerate(parsed_events):
            if ev["start_dt"] <= now < ev["end_dt"]:
                current_event = ev
                # Look for next event after this one
                for j in range(i + 1, len(parsed_events)):
                    candidate = parsed_events[j]
                    try:
                        candidate_temp = float(candidate["state"])
                        current_temp = float(ev["state"])
                        if candidate_temp > current_temp + 0.3:
                            next_event = candidate
                            break
                    except (ValueError, TypeError):
                        continue
                break

        if next_event is None:
            # Check tomorrow's first heating-up event
            tomorrow = today + timedelta(days=1)
            tomorrow_weekday = tomorrow.strftime("%A").lower()
            for event in events:
                ev = self._parse_single_event(event, tomorrow, tomorrow_weekday)
                if ev:
                    try:
                        ev_temp = float(ev["state"])
                        if ev_temp > current_consigne + 0.3:
                            next_event = ev
                            break
                    except (ValueError, TypeError):
                        continue

        if next_event is None:
            return None

        try:
            target_temp = float(next_event["state"])
        except (ValueError, TypeError):
            return None

        return NextTransition(
            target_time=next_event["start_dt"],
            target_temp=target_temp,
            current_temp_schedule=current_consigne,
            source="schedule_state",
        )

    def _parse_single_event(
        self, event: dict, date: Any, weekday: str
    ) -> dict | None:
        """Parse a single schedule event into start/end datetimes."""
        # Check if event applies to this day
        days = event.get("days")
        if days and isinstance(days, list):
            day_names = [d.lower() for d in days]
            if weekday not in day_names:
                return None

        # Parse times
        start_str = event.get("start") or event.get("from") or event.get("time_start")
        end_str = event.get("end") or event.get("to") or event.get("time_end")
        state_val = event.get("state") or event.get("value") or event.get("temperature")

        if not start_str or not state_val:
            return None

        try:
            start_time = self._parse_time(start_str)
            start_dt = datetime.combine(date, start_time)

            if end_str:
                end_time = self._parse_time(end_str)
                end_dt = datetime.combine(date, end_time)
                # Handle overnight
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
            else:
                end_dt = start_dt + timedelta(hours=23, minutes=59)

            return {
                "start_dt": start_dt,
                "end_dt": end_dt,
                "state": str(state_val),
            }
        except (ValueError, TypeError) as e:
            _LOGGER.debug("Error parsing event %s: %s", event, e)
            return None

    def _parse_time(self, time_str: str) -> dt_time:
        """Parse time string in various formats."""
        time_str = str(time_str).strip()
        for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p"):
            try:
                return datetime.strptime(time_str, fmt).time()
            except ValueError:
                continue
        raise ValueError(f"Cannot parse time: {time_str}")

    def _parse_vtherm_attrs(
        self, state: Any, current_consigne: float
    ) -> NextTransition | None:
        """Parse VTherm-style attributes for preset info."""
        attrs = state.attributes

        # VTherm exposes comfort/eco/boost temps as attributes
        comfort_temp = attrs.get("comfort_temp") or attrs.get("comfort")
        eco_temp = attrs.get("eco_temp") or attrs.get("eco")
        current_preset = attrs.get("preset_mode")

        if comfort_temp is not None and eco_temp is not None:
            try:
                comfort = float(comfort_temp)
                eco = float(eco_temp)

                # If currently in eco and comfort is higher, next transition is to comfort
                if current_consigne <= eco + 0.3 and comfort > eco + 0.3:
                    return NextTransition(
                        target_time=None,  # Don't know when
                        target_temp=comfort,
                        current_temp_schedule=current_consigne,
                        source="vtherm_preset",
                    )
            except (ValueError, TypeError):
                pass

        return None

    def get_all_transitions_today(self) -> list[NextTransition]:
        """Get all transitions for today (for display purposes)."""
        if not self.schedule_entity:
            return []

        state = self.hass.states.get(self.schedule_entity)
        if state is None:
            return []

        try:
            current_consigne = float(state.state)
        except (ValueError, TypeError):
            return []

        events = state.attributes.get("events", [])
        if not events:
            return []

        now = datetime.now()
        today = now.date()
        weekday = now.strftime("%A").lower()

        transitions = []
        prev_temp = None

        parsed = []
        for event in events:
            ev = self._parse_single_event(event, today, weekday)
            if ev:
                parsed.append(ev)

        parsed.sort(key=lambda e: e["start_dt"])

        for ev in parsed:
            try:
                temp = float(ev["state"])
            except (ValueError, TypeError):
                continue

            if prev_temp is not None and abs(temp - prev_temp) > 0.1:
                transitions.append(
                    NextTransition(
                        target_time=ev["start_dt"],
                        target_temp=temp,
                        current_temp_schedule=prev_temp,
                        source="schedule_state",
                    )
                )
            prev_temp = temp

        return transitions
