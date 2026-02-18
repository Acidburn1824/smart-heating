"""Feedback loop - measures anticipation accuracy and auto-adjusts margin.

After each anticipation cycle, we record:
- Did we reach target temp on time?
- How many minutes early/late?
- What was the margin used?

Over time, this data is used to auto-calibrate the safety margin
so we're consistently arriving 2-5 minutes early (not 15 min early
wasting energy, not 5 min late causing discomfort).
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

_LOGGER = logging.getLogger(__name__)

TARGET_EARLY_MINUTES = 3.0  # We want to arrive 3 min early ideally
MARGIN_ADJUST_STEP = 0.02  # 2% adjustment per feedback cycle
MAX_HISTORY = 30  # Keep last 30 anticipation results


@dataclass
class AnticipationResult:
    """Result of a completed anticipation cycle."""

    date: str
    target_temp: float
    actual_temp_at_target_time: float
    temp_at_start: float
    target_time: str  # ISO format
    actual_arrival_time: str | None  # When target was actually reached
    minutes_early: float  # Positive = early, negative = late
    margin_used: float  # Safety margin that was used
    llm_adjustment: float  # LLM adjustment that was active
    ext_temp_avg: float
    success: bool  # Did we reach target temp?

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "target_temp": self.target_temp,
            "actual_temp_at_target_time": self.actual_temp_at_target_time,
            "temp_at_start": self.temp_at_start,
            "target_time": self.target_time,
            "actual_arrival_time": self.actual_arrival_time,
            "minutes_early": self.minutes_early,
            "margin_used": self.margin_used,
            "llm_adjustment": self.llm_adjustment,
            "ext_temp_avg": self.ext_temp_avg,
            "success": self.success,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AnticipationResult:
        return cls(**{k: data[k] for k in data if k in cls.__dataclass_fields__})


class FeedbackLoop:
    """Tracks anticipation results and auto-adjusts margin."""

    def __init__(self, zone_name: str) -> None:
        self.zone_name = zone_name
        self.history: list[AnticipationResult] = []
        self._pending_start: dict[str, Any] | None = None

    def load_history(self, data: list[dict]) -> None:
        """Load from persisted data."""
        try:
            self.history = [AnticipationResult.from_dict(d) for d in data]
        except Exception as e:
            _LOGGER.error("[%s] Error loading feedback history: %s", self.zone_name, e)
            self.history = []

    def get_history_data(self) -> list[dict]:
        """Export for storage."""
        return [r.to_dict() for r in self.history[-MAX_HISTORY:]]

    def start_tracking(
        self,
        target_temp: float,
        target_time: datetime,
        temp_at_start: float,
        margin_used: float,
        llm_adjustment: float,
        ext_temp: float,
    ) -> None:
        """Start tracking an anticipation cycle."""
        self._pending_start = {
            "target_temp": target_temp,
            "target_time": target_time,
            "temp_at_start": temp_at_start,
            "margin_used": margin_used,
            "llm_adjustment": llm_adjustment,
            "ext_temp": ext_temp,
            "started_at": datetime.now(),
        }
        _LOGGER.debug(
            "[%s] Feedback: tracking started for %.1f°C at %s",
            self.zone_name, target_temp, target_time.strftime("%H:%M"),
        )

    def record_result(
        self,
        current_temp: float,
        reached_target: bool,
    ) -> AnticipationResult | None:
        """Record the result when anticipation ends.

        Call this when:
        - Target temp is reached (success)
        - Target time passed (check if we made it)
        - Anticipation was cancelled
        """
        if self._pending_start is None:
            return None

        pending = self._pending_start
        self._pending_start = None

        now = datetime.now()
        target_time: datetime = pending["target_time"]

        # Calculate minutes early/late
        if reached_target:
            minutes_early = (target_time - now).total_seconds() / 60
            actual_arrival = now.isoformat()
        else:
            minutes_early = -((now - target_time).total_seconds() / 60)
            actual_arrival = None

        result = AnticipationResult(
            date=now.strftime("%Y-%m-%d %H:%M"),
            target_temp=pending["target_temp"],
            actual_temp_at_target_time=current_temp,
            temp_at_start=pending["temp_at_start"],
            target_time=target_time.isoformat(),
            actual_arrival_time=actual_arrival,
            minutes_early=round(minutes_early, 1),
            margin_used=pending["margin_used"],
            llm_adjustment=pending["llm_adjustment"],
            ext_temp_avg=pending["ext_temp"],
            success=reached_target,
        )

        self.history.append(result)
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

        log_level = logging.INFO if reached_target else logging.WARNING
        _LOGGER.log(
            log_level,
            "[%s] Feedback: %s | %.1f°C %s (%.1f min %s) | marge: %.0f%%",
            self.zone_name,
            "✅ Succès" if reached_target else "⚠️ En retard",
            current_temp,
            f"→ {pending['target_temp']}°C",
            abs(minutes_early),
            "en avance" if minutes_early > 0 else "en retard",
            pending["margin_used"] * 100,
        )

        return result

    def get_margin_suggestion(self) -> float | None:
        """Calculate suggested margin adjustment based on recent results.

        Returns a delta to apply to the current margin, or None if not enough data.

        Logic:
        - If we're consistently arriving too early → reduce margin
        - If we're consistently arriving late → increase margin
        - Target: arrive 2-5 minutes early
        """
        recent = [r for r in self.history[-10:] if r.success is not None]
        if len(recent) < 3:
            return None

        avg_early = statistics.mean(r.minutes_early for r in recent)
        success_rate = sum(1 for r in recent if r.success) / len(recent)

        # Target: 2-5 minutes early
        if avg_early > 10:
            # Way too early - we're wasting energy
            adjustment = -MARGIN_ADJUST_STEP * 2
            _LOGGER.info(
                "[%s] Feedback: trop en avance (%.0f min avg), réduction marge",
                self.zone_name, avg_early,
            )
        elif avg_early > 5:
            # A bit too early
            adjustment = -MARGIN_ADJUST_STEP
        elif avg_early < 0:
            # Arriving late!
            adjustment = MARGIN_ADJUST_STEP * 2
            _LOGGER.warning(
                "[%s] Feedback: en retard (%.0f min avg), augmentation marge",
                self.zone_name, avg_early,
            )
        elif avg_early < 2:
            # Cutting it close
            adjustment = MARGIN_ADJUST_STEP
        else:
            # Sweet spot (2-5 min early) - no change
            adjustment = 0.0

        # Also check success rate
        if success_rate < 0.7:
            # Less than 70% success - increase margin
            adjustment = max(adjustment, MARGIN_ADJUST_STEP * 2)
            _LOGGER.warning(
                "[%s] Feedback: taux de succès faible (%.0f%%), augmentation marge",
                self.zone_name, success_rate * 100,
            )

        return round(adjustment, 3)

    @property
    def stats(self) -> dict[str, Any]:
        """Get feedback statistics."""
        if not self.history:
            return {
                "total_cycles": 0,
                "success_rate": None,
                "avg_minutes_early": None,
                "suggested_adjustment": None,
            }

        recent = self.history[-10:]
        successes = [r for r in recent if r.success]

        return {
            "total_cycles": len(self.history),
            "recent_cycles": len(recent),
            "success_rate": round(len(successes) / len(recent) * 100, 0) if recent else None,
            "avg_minutes_early": round(
                statistics.mean(r.minutes_early for r in recent), 1
            ) if recent else None,
            "last_result": recent[-1].to_dict() if recent else None,
            "suggested_adjustment": self.get_margin_suggestion(),
        }
