"""Simulated time is the only time this package knows.

Every component that needs "now" takes a Clock, because a monitoring tool whose
library code calls datetime.now() cannot be tested without sleeping, and a
loaded CI runner turns a sleeping test into a flake. Time here is a float day
count from stream start; nothing in src/ reads the wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass


class ClockError(ValueError):
    """Raised when a clock is asked to move backwards."""


@dataclass
class SimClock:
    """A settable day counter. Monotone by construction."""

    day: float = 0.0

    def now(self) -> float:
        return self.day

    def advance_to(self, day: float) -> float:
        if day < self.day:
            raise ClockError(f"clock cannot move from day {self.day} back to day {day}")
        self.day = float(day)
        return self.day

    def advance_by(self, days: float) -> float:
        if days < 0:
            raise ClockError(f"cannot advance by a negative span ({days})")
        return self.advance_to(self.day + days)
