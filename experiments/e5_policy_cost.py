"""E5: which retraining trigger costs least, in the units an operator pays?

Every label-confirmed retrain is also registered in an MLflow registry
(SQLite, in a scratch directory) with its serving start and trigger reason,
so the registry claim in ADR-004 is exercised by the experiment that makes
it, and the count of registered versions is recorded in the output.

Sixty streams: real regressions at staggered onsets (half of them also moving
the covariates, E4's co-shift assumption), harmless shifts, and clean weeks,
at a higher harm density than E4 so each policy meets enough incidents. Each policy sees identical streams and only day-by-day observable data.
Costs: predictions served while degraded (missed harm) and retrains fired with
no regression to fix (wasted). The retrain itself is a best case for every
policy (ADR-004), so the differences below belong to the triggers.
"""

from __future__ import annotations

import json
import tempfile

import numpy as np
from common import build, write

from blind_window.policy.retrain import drift_triggered, label_confirmed, scheduled
from blind_window.power import OperatingPoint
from blind_window.simulate.stream import generate

HORIZON = 100.0
RATE = 500.0
MEDIAN_DELAY = 21.0
TARGET_DROP_PTS = 2.0
SCHEDULE_DAYS = 30.0
BASE_SEED = 600

N_HARM = 30
HARM_WITH_SHIFT = 15
N_HARMLESS = 15
N_CLEAN = 15


def _streams():
    onsets = np.linspace(25.0, 60.0, N_HARM)
    idx = 0
    for i in range(N_HARM):
        with_shift = i < HARM_WITH_SHIFT
        yield build(
            f"e5_harm_{i}",
            seed=BASE_SEED + idx,
            horizon=HORIZON,
            rate=RATE,
            median_delay=MEDIAN_DELAY,
            input_mag=1.0 if with_shift else 0.0,
            input_onset=float(onsets[i]) if with_shift else None,
            drop_pts=4.0,
            concept_onset=float(onsets[i]),
        )
        idx += 1
    for i in range(N_HARMLESS):
        yield build(
            f"e5_harmless_{i}",
            seed=BASE_SEED + idx,
            horizon=HORIZON,
            rate=RATE,
            median_delay=MEDIAN_DELAY,
            input_mag=1.0,
            input_onset=float(25.0 + i),
        )
        idx += 1
    for i in range(N_CLEAN):
        yield build(
            f"e5_clean_{i}",
            seed=BASE_SEED + idx,
            horizon=HORIZON,
            rate=RATE,
            median_delay=MEDIAN_DELAY,
        )
        idx += 1


def run() -> dict:
    op = OperatingPoint()
    totals = {
        "drift_triggered": {"exposed": 0, "wasted": 0, "retrains": 0, "harm_missed_entirely": 0},
        "scheduled_30d": {"exposed": 0, "wasted": 0, "retrains": 0, "harm_missed_entirely": 0},
        "label_confirmed": {"exposed": 0, "wasted": 0, "retrains": 0, "harm_missed_entirely": 0},
    }
    n_harm_streams = 0
    registered = 0
    from blind_window.registry import Registry

    with tempfile.TemporaryDirectory() as reg_dir:
        registry = Registry(reg_dir)
        for sc in _streams():
            s = generate(sc)
            is_harm = s.meta["concept_onset_day"] is not None
            n_harm_streams += int(is_harm)
            for out in (
                drift_triggered(s),
                scheduled(s, SCHEDULE_DAYS),
                label_confirmed(s, TARGET_DROP_PTS, op),
            ):
                key = out.policy
                totals[key]["exposed"] += out.exposed_predictions
                totals[key]["wasted"] += out.wasted_retrains
                totals[key]["retrains"] += out.n_retrains
                if is_harm and out.harm_end_day is None:
                    totals[key]["harm_missed_entirely"] += 1
                if key == "label_confirmed":
                    for day in out.retrain_days:
                        registry.record_version(
                            day, f"label_confirmed retrain, stream {sc.name}"
                        )
                        registered += 1
        registered_in_registry = len(registry.versions())

    payload = {
        "design": {
            "n_streams": N_HARM + N_HARMLESS + N_CLEAN,
            "n_harm": N_HARM,
            "harm_with_shift": HARM_WITH_SHIFT,
            "n_harmless_shift": N_HARMLESS,
            "n_clean": N_CLEAN,
            "schedule_days": SCHEDULE_DAYS,
            "target_drop_pts": TARGET_DROP_PTS,
            "retrain_model": "best case: realigns with the current concept on the retrain day",
        },
        "measurements": {k: dict(v) for k, v in totals.items()},
    }
    payload["measurements"]["n_harm_streams"] = n_harm_streams
    payload["measurements"]["label_confirmed_retrains_registered"] = registered
    if registered != registered_in_registry:
        raise RuntimeError(
            f"registered {registered} retrains but the registry lists "
            f"{registered_in_registry}"
        )
    write("e5_policy_cost.json", payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run()["measurements"], indent=2))
