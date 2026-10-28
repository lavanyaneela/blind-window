"""Scenario configuration: everything a stream needs to be replayed exactly.

A scenario is a committed JSON file, not code, so a reviewer can read what was
injected and when without tracing the simulator. Validation lives here because
a scenario with a drift event outside the horizon or a delay distribution with
negative mass would produce a stream whose ground truth is wrong, and every
number downstream inherits that.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

VALID_DELAY_KINDS = ("lognormal", "gamma", "fixed")
VALID_DRIFT_KINDS = ("input_shift", "concept_shift")
VALID_DELAY_COUPLING = ("none", "hard_cases_slower")


class ScenarioError(ValueError):
    """Raised when a scenario file cannot define a valid stream."""


@dataclass(frozen=True)
class DelaySpec:
    """Label delay distribution in days. A distribution, not a constant: the
    spread is what makes the blind window a curve rather than a date."""

    kind: str
    median_days: float
    sigma: float = 0.6  # lognormal shape / gamma cv proxy; ignored for fixed
    coupling: str = "none"
    coupling_strength: float = 0.0

    def validate(self) -> None:
        if self.kind not in VALID_DELAY_KINDS:
            raise ScenarioError(f"unknown delay kind {self.kind!r}")
        if not (self.median_days >= 0):
            raise ScenarioError("median_days must be non-negative")
        if self.kind != "fixed" and not (self.sigma > 0):
            raise ScenarioError("sigma must be positive for a spread distribution")
        if self.coupling not in VALID_DELAY_COUPLING:
            raise ScenarioError(f"unknown delay coupling {self.coupling!r}")
        if self.coupling == "none" and self.coupling_strength != 0.0:
            raise ScenarioError("coupling_strength must be 0 when coupling is none")
        if self.coupling_strength < 0:
            raise ScenarioError("coupling_strength must be non-negative")


@dataclass(frozen=True)
class DriftEvent:
    """One injected change, with ground truth attached.

    input_shift moves the covariate mean along a direction orthogonal to the
    concept, so it is visible to input detectors and costless to accuracy.
    concept_shift rotates the concept by an angle chosen to produce a stated
    accuracy drop, and leaves the covariate distribution untouched. The two are
    injectable independently, which is the property E1 depends on.
    """

    kind: str
    onset_day: float
    magnitude: float  # input_shift: mean shift in sd units; concept_shift: accuracy drop in points

    def validate(self, horizon_days: float) -> None:
        if self.kind not in VALID_DRIFT_KINDS:
            raise ScenarioError(f"unknown drift kind {self.kind!r}")
        if not (0 <= self.onset_day < horizon_days):
            raise ScenarioError(
                f"drift onset day {self.onset_day} outside horizon [0, {horizon_days})"
            )
        if self.magnitude < 0:
            raise ScenarioError("drift magnitude must be non-negative")
        if self.kind == "concept_shift" and self.magnitude >= 50:
            raise ScenarioError("concept_shift magnitude is an accuracy drop in points, below 50")


@dataclass(frozen=True)
class Scenario:
    name: str
    seed: int
    horizon_days: float
    rate_per_day: float
    n_features: int
    delay: DelaySpec
    drifts: tuple[DriftEvent, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if not (self.horizon_days > 0):
            raise ScenarioError("horizon_days must be positive")
        if not (self.rate_per_day > 0):
            raise ScenarioError("rate_per_day must be positive")
        if self.n_features < 2:
            raise ScenarioError("need at least 2 features to build an orthogonal shift")
        if not math.isfinite(self.horizon_days * self.rate_per_day):
            raise ScenarioError("horizon times rate must be finite")
        self.delay.validate()
        for d in self.drifts:
            d.validate(self.horizon_days)

    @staticmethod
    def from_dict(raw: dict) -> "Scenario":
        try:
            delay = DelaySpec(**raw["delay"])
            drifts = tuple(DriftEvent(**d) for d in raw.get("drifts", []))
            sc = Scenario(
                name=str(raw["name"]),
                seed=int(raw["seed"]),
                horizon_days=float(raw["horizon_days"]),
                rate_per_day=float(raw["rate_per_day"]),
                n_features=int(raw.get("n_features", 6)),
                delay=delay,
                drifts=drifts,
            )
        except (KeyError, TypeError) as exc:
            raise ScenarioError(f"scenario file is missing or mistypes a field: {exc}") from exc
        sc.validate()
        return sc

    @staticmethod
    def load(path: str | Path) -> "Scenario":
        p = Path(path)
        if not p.exists():
            raise ScenarioError(f"scenario file not found: {p}")
        try:
            raw = json.loads(p.read_text())
        except json.JSONDecodeError as exc:
            raise ScenarioError(f"scenario file is not valid JSON: {p}: {exc}") from exc
        return Scenario.from_dict(raw)
