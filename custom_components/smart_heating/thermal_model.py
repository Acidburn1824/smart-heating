"""Thermal model - learns heating inertia from historical sessions."""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

_LOGGER = logging.getLogger(__name__)


@dataclass
class HeatingSession:
    """A single heating session record."""

    date: str
    temp_start: float
    temp_end: float
    temp_ext_avg: float
    delta_temp: float
    duration_min: float
    speed_degc_per_min: float
    anticipated: bool = False
    points: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "temp_start": self.temp_start,
            "temp_end": self.temp_end,
            "temp_ext_avg": self.temp_ext_avg,
            "delta_temp": self.delta_temp,
            "duration_min": self.duration_min,
            "speed_degc_per_min": self.speed_degc_per_min,
            "anticipated": self.anticipated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> HeatingSession:
        return cls(
            date=data.get("date", ""),
            temp_start=data.get("temp_start", 0),
            temp_end=data.get("temp_end", 0),
            temp_ext_avg=data.get("temp_ext_avg", 0),
            delta_temp=data.get("delta_temp", 0),
            duration_min=data.get("duration_min", 0),
            speed_degc_per_min=data.get("speed_degc_per_min", 0),
            anticipated=data.get("anticipated", False),
        )


class ThermalModel:
    """Learns and predicts heating behavior from session data."""

    def __init__(self, warmup_ignore_min: float = 0) -> None:
        self.sessions: list[HeatingSession] = []
        self.warmup_ignore_min = warmup_ignore_min
        self._inertia: dict[str, Any] = {}

    def load_sessions(self, data: list[dict]) -> None:
        """Load sessions from stored data."""
        self.sessions = [HeatingSession.from_dict(s) for s in data]
        self._recalculate()

    def add_session(self, session: HeatingSession) -> None:
        """Add a new session and recalculate."""
        self.sessions.append(session)
        # Keep max 100 sessions
        if len(self.sessions) > 100:
            self.sessions = self.sessions[-100:]
        self._recalculate()

    def get_sessions_data(self) -> list[dict]:
        """Export sessions for storage."""
        return [s.to_dict() for s in self.sessions]

    @property
    def num_sessions(self) -> int:
        return len(self.sessions)

    @property
    def avg_speed(self) -> float | None:
        """Average heating speed in °C/min."""
        return self._inertia.get("avg_speed")

    @property
    def min_per_deg(self) -> float | None:
        """Average minutes to gain 1°C."""
        speed = self.avg_speed
        if speed and speed > 0:
            return round(1.0 / speed, 1)
        return None

    @property
    def inertia_data(self) -> dict[str, Any]:
        """Full inertia data for LLM context."""
        return self._inertia.copy()

    def estimate_time_to_target(
        self,
        current_temp: float,
        target_temp: float,
        ext_temp: float,
        margin: float = 1.15,
    ) -> float | None:
        """Estimate minutes needed to reach target temp.

        Args:
            current_temp: Current indoor temperature
            target_temp: Target temperature
            ext_temp: Current outdoor temperature
            margin: Safety margin multiplier

        Returns:
            Estimated minutes, or None if not enough data
        """
        delta = target_temp - current_temp
        if delta <= 0:
            return 0

        # Try to find speed for similar ext temp
        speed = self._get_speed_for_ext_temp(ext_temp)
        if speed is None or speed <= 0:
            return None

        base_minutes = delta / speed
        return round(base_minutes * margin, 0)

    def _get_speed_for_ext_temp(self, ext_temp: float) -> float | None:
        """Get heating speed adapted to outdoor temperature."""
        if not self.sessions:
            return None

        # Group sessions by ext temp ranges (5°C buckets)
        bucket = round(ext_temp / 5) * 5
        nearby_sessions = [
            s for s in self.sessions
            if abs(s.temp_ext_avg - bucket) <= 5
        ]

        if nearby_sessions:
            speeds = [s.speed_degc_per_min for s in nearby_sessions if s.speed_degc_per_min > 0]
            if speeds:
                return statistics.median(speeds)

        # Fallback to global average
        return self.avg_speed

    def _recalculate(self) -> None:
        """Recalculate inertia statistics from all sessions."""
        if not self.sessions:
            self._inertia = {}
            return

        valid = [s for s in self.sessions if s.speed_degc_per_min > 0 and s.duration_min >= 5]
        if not valid:
            self._inertia = {}
            return

        speeds = [s.speed_degc_per_min for s in valid]

        # By ext temp bucket
        by_ext = {}
        for s in valid:
            bucket = str(round(s.temp_ext_avg / 5) * 5)
            if bucket not in by_ext:
                by_ext[bucket] = []
            by_ext[bucket].append(s.speed_degc_per_min)

        by_ext_avg = {k: round(statistics.mean(v), 5) for k, v in by_ext.items()}

        self._inertia = {
            "avg_speed": round(statistics.mean(speeds), 5),
            "median_speed": round(statistics.median(speeds), 5),
            "min_speed": round(min(speeds), 5),
            "max_speed": round(max(speeds), 5),
            "num_sessions": len(valid),
            "min_per_deg": round(1.0 / statistics.mean(speeds), 1) if statistics.mean(speeds) > 0 else None,
            "by_ext_temp": by_ext_avg,
        }
