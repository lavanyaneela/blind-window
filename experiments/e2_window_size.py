"""E2: how long is the blind window, and what ships inside it?

The window as a function of median label delay and traffic rate, for a fixed
target drop at the default operating point. The headline cell is not from this
grid: it is measured on the committed default scenario fixture itself, so the
number on the README's first screen is the number `make demo` reproduces.
"""

from __future__ import annotations

import json

import numpy as np
from common import DEFAULT_SCENARIO, build, write

from blind_window.power import OperatingPoint, blind_window
from blind_window.scenario import Scenario
from blind_window.simulate.stream import generate

MEDIAN_DELAYS = (3.0, 7.0, 14.0, 21.0, 35.0)
RATES = (200.0, 800.0, 3200.0)
TARGET_DROP_PTS = 2.0
ONSET = 30.0
HORIZON = 150.0
GRID_SEED = 401


def _window_for(stream, onset: float, horizon: float):
    correct = stream.predicted == stream.y_true
    base_mask = (stream.ts_day < onset) & (stream.label_day <= onset)
    # Baseline accuracy estimated from what was labeled by onset; when the
    # delay is long that sample can be empty, so fall back to the first day
    # with any labeled baseline, which the walk handles via maturing counts.
    if base_mask.any():
        acc0 = float(np.mean(correct[base_mask]))
    else:
        acc0 = float(np.mean(correct[stream.ts_day < onset]))
    return blind_window(
        stream.ts_day,
        stream.label_day,
        onset,
        horizon,
        acc0,
        TARGET_DROP_PTS,
        OperatingPoint(),
    )


def run() -> dict:
    cells = []
    for md in MEDIAN_DELAYS:
        for rate in RATES:
            sc = build(
                f"e2_md{md}_r{rate}",
                seed=GRID_SEED,
                horizon=HORIZON,
                rate=rate,
                median_delay=md,
                drop_pts=4.0,
                concept_onset=ONSET,
            )
            s = generate(sc)
            bw = _window_for(s, ONSET, HORIZON)
            cells.append(
                {
                    "median_delay_days": md,
                    "rate_per_day": rate,
                    "blind_days": bw.blind_days,
                    "answerable": bw.answerable_day is not None,
                    "predictions_in_window": bw.predictions_in_window,
                }
            )
    default = Scenario.load(DEFAULT_SCENARIO)
    ds = generate(default)
    onset = float(ds.meta["concept_onset_day"])
    dbw = _window_for(ds, onset, default.horizon_days)
    payload = {
        "design": {
            "median_delays": MEDIAN_DELAYS,
            "rates": RATES,
            "target_drop_pts": TARGET_DROP_PTS,
            "operating_point": {"alpha": 0.05, "power": 0.8},
        },
        "measurements": {
            "default_blind_days": dbw.blind_days,
            "default_blind_predictions": dbw.predictions_in_window,
            "default_answerable_day": dbw.answerable_day,
            "default_median_delay_days": default.delay.median_days,
            "default_rate_per_day": default.rate_per_day,
            "min_blind_days_on_grid": min(c["blind_days"] for c in cells),
            "max_blind_days_on_grid": max(c["blind_days"] for c in cells),
            "rate_16x_shrinks_window_by": _rate_effect(cells),
        },
        "cells": cells,
    }
    write("e2_window_size.json", payload)
    return payload


def _rate_effect(cells: list[dict]) -> float:
    """How much a 16x traffic increase shrinks the window at the default delay.

    Traffic multiplies the labeled sample but the delay distribution still
    gates when those labels exist, so the window shrinks far less than 16x.
    This ratio is that finding as one number.
    """
    at_md = {c["rate_per_day"]: c["blind_days"] for c in cells if c["median_delay_days"] == 21.0}
    return float(at_md[200.0] / at_md[3200.0])


if __name__ == "__main__":
    print(json.dumps(run()["measurements"], indent=2))
