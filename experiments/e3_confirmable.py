"""E3: what is confirmable, and when?

The minimum confirmable drop at day 1, 7 and 30 after onset on the default
stream, plus the censoring arm (E3b): when label delay is coupled to case
difficulty, the labels available early are not a random sample of traffic, and
the early accuracy estimate is biased before any test is run. That bias is
measured here in points and carried by ADR-005.
"""

from __future__ import annotations

import json

import numpy as np
from common import DEFAULT_SCENARIO, build, write

from blind_window.power import OperatingPoint, min_detectable_drop
from blind_window.scenario import Scenario
from blind_window.simulate.stream import generate

CHECK_DAYS = (1.0, 7.0, 30.0)
COUPLING_STRENGTH = 1.2
E3B_SEED = 403


def _mdd_at(stream, onset: float, asof: float) -> float | None:
    correct = stream.predicted == stream.y_true
    base = (stream.ts_day < onset) & (stream.label_day <= asof)
    post = (stream.ts_day >= onset) & (stream.label_day <= asof)
    if not base.any() or not post.any():
        return None
    acc0 = float(np.mean(correct[base]))
    return min_detectable_drop(acc0, int(base.sum()), int(post.sum()), OperatingPoint())


def run() -> dict:
    default = Scenario.load(DEFAULT_SCENARIO)
    ds = generate(default)
    onset = float(ds.meta["concept_onset_day"])
    mdd = {}
    for d in CHECK_DAYS:
        v = _mdd_at(ds, onset, onset + d)
        mdd[f"day{int(d)}"] = v

    # E3b: couple delay to difficulty. Easy cases (confident scores) come back
    # first; pre-onset, easy cases are also the ones the model gets right, so
    # the early labeled sample over-represents correct predictions on both
    # sides of the onset. The bias below is early-labeled accuracy minus the
    # full-cohort accuracy for the same post-onset cohort.
    coupled = build(
        "e3b_coupled",
        seed=E3B_SEED,
        horizon=default.horizon_days,
        rate=default.rate_per_day,
        median_delay=default.delay.median_days,
        drop_pts=4.0,
        concept_onset=onset,
        coupling="hard_cases_slower",
        coupling_strength=COUPLING_STRENGTH,
    )
    cs = generate(coupled)
    correct = cs.predicted == cs.y_true
    cohort = cs.ts_day >= onset
    early = cohort & (cs.label_day <= onset + 7.0)
    bias_pts = (float(np.mean(correct[early])) - float(np.mean(correct[cohort]))) * 100.0
    uncoupled_early = (ds.ts_day >= onset) & (ds.label_day <= onset + 7.0)
    ds_correct = ds.predicted == ds.y_true
    bias_uncoupled_pts = (
        float(np.mean(ds_correct[uncoupled_early])) - float(np.mean(ds_correct[ds.ts_day >= onset]))
    ) * 100.0

    payload = {
        "design": {
            "check_days": CHECK_DAYS,
            "operating_point": {"alpha": 0.05, "power": 0.8},
            "coupling_strength": COUPLING_STRENGTH,
        },
        "measurements": {
            "mdd_day1_pts": mdd["day1"],
            "mdd_day7_pts": mdd["day7"],
            "mdd_day30_pts": mdd["day30"],
            "early_label_bias_coupled_pts": bias_pts,
            "early_label_bias_uncoupled_pts": bias_uncoupled_pts,
            "n_early_labeled_coupled_day7": int(early.sum()),
        },
    }
    write("e3_confirmable.json", payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run()["measurements"], indent=2))
