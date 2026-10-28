"""Retraining trigger policies, priced on what each one actually costs.

Three triggers compete: retrain on an input drift alarm, retrain on a fixed
schedule, retrain when a regression is label-confirmed. Each is evaluated on
the same simulated streams using only information observable on the day of the
decision. The retrain itself is a best case (the model realigns with the
current concept immediately), stated in ADR-004: with the fix held constant,
every cost difference is attributable to the trigger.

Costs are counted in the units an operator pays: predictions served while the
model is degraded (missed harm), and retrains fired with no active regression
to fix (wasted retrains).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from blind_window.detectors.input_side import psi
from blind_window.power import OperatingPoint, judge
from blind_window.simulate.stream import Stream

REFERENCE_DAYS = 10.0
CHECK_WINDOW_DAYS = 7.0


class PolicyError(ValueError):
    """Raised when a policy is configured in a way that cannot be evaluated."""


@dataclass(frozen=True)
class PolicyOutcome:
    policy: str
    retrain_days: tuple[float, ...]
    harm_onset_day: float | None
    harm_end_day: float | None  # first retrain at or after onset; None when harm never ends
    exposed_predictions: int  # served between onset and harm end (or horizon)
    n_retrains: int
    wasted_retrains: int


def _exposure(stream: Stream, onset: float | None, end: float | None) -> int:
    if onset is None:
        return 0
    stop = end if end is not None else float(stream.scenario.horizon_days)
    return int(np.count_nonzero((stream.ts_day >= onset) & (stream.ts_day < stop)))


def _outcome(stream: Stream, name: str, retrain_days: list[float]) -> PolicyOutcome:
    onset = stream.meta.get("concept_onset_day")
    after = [d for d in retrain_days if onset is not None and d >= onset]
    harm_end = min(after) if after else None
    wasted = len(retrain_days) - (1 if harm_end is not None else 0)
    return PolicyOutcome(
        policy=name,
        retrain_days=tuple(retrain_days),
        harm_onset_day=onset,
        harm_end_day=harm_end,
        exposed_predictions=_exposure(stream, onset, harm_end),
        n_retrains=len(retrain_days),
        wasted_retrains=wasted,
    )


def drift_triggered(stream: Stream, check_every_days: float = 1.0) -> PolicyOutcome:
    """Retrain the first time the worst-feature PSI crosses its threshold.

    One retrain at most: the alarm compares against the pre-deployment
    reference, so once it is latched it stays latched, and counting every
    subsequent day as another retrain would bill the policy for the same alarm
    daily. The alarm sees covariates only, which is the whole finding.
    """
    if check_every_days <= 0:
        raise PolicyError("check cadence must be positive days")
    ref = stream.features[stream.ts_day < REFERENCE_DAYS]
    if ref.shape[0] < 50:
        raise PolicyError("reference window has too few rows to fit PSI bins")
    retrains: list[float] = []
    day = REFERENCE_DAYS + CHECK_WINDOW_DAYS
    while day <= stream.scenario.horizon_days:
        win = stream.features[(stream.ts_day >= day - CHECK_WINDOW_DAYS) & (stream.ts_day < day)]
        if win.shape[0] >= 50:
            worst = max(
                psi(ref[:, j], win[:, j]).score for j in range(stream.features.shape[1])
            )
            if worst >= 0.2:
                retrains.append(float(day))
                break
        day += check_every_days
    return _outcome(stream, "drift_triggered", retrains)


def scheduled(stream: Stream, every_days: float) -> PolicyOutcome:
    """Retrain on a fixed cadence, blind to everything."""
    if every_days <= 0:
        raise PolicyError("schedule cadence must be positive days")
    retrains = list(
        np.arange(every_days, stream.scenario.horizon_days + 1e-9, every_days, dtype=float)
    )
    return _outcome(stream, f"scheduled_{int(every_days)}d", retrains)


def label_confirmed(
    stream: Stream, target_drop_points: float, op: OperatingPoint, check_every_days: float = 1.0
) -> PolicyOutcome:
    """Retrain on the first day a regression is label-confirmed (exit 0).

    The policy this repository argues for, and the one the blind window taxes:
    it can never act earlier than the labels allow. Candidate onsets are the
    drift alarm day when one fired, else a rolling suspicion window; here the
    simulator's true onset is used as the hypothesis under test, which favours
    this policy and is disclosed in ADR-004 (it bounds the policy's best case).
    """
    if check_every_days <= 0:
        raise PolicyError("check cadence must be positive days")
    onset = stream.meta.get("concept_onset_day")
    if onset is None:
        return _outcome(stream, "label_confirmed", [])
    correct = (stream.predicted == stream.y_true).astype(np.int8)
    day = float(onset) + check_every_days
    while day <= stream.scenario.horizon_days:
        base = (stream.ts_day < onset) & (stream.label_day <= day)
        post = (stream.ts_day >= onset) & (stream.label_day <= day)
        if base.any():
            v = judge(correct[base], correct[post], target_drop_points, op)
            if v.exit_code == 0:
                return _outcome(stream, "label_confirmed", [day])
        day += check_every_days
    return _outcome(stream, "label_confirmed", [])
