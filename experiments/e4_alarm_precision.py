"""E4: how often does the input alarm lie, at the base rate it will really see?

Precision depends on prevalence far more than on the detector. A monitoring
quarter is simulated as independent periods: most contain nothing, some contain
a harmless covariate shift, a few contain a real regression, and half of the
real regressions also move the covariates (the generous assumption; a pure
concept shift moves nothing). The alarm is the standard one: worst-feature PSI
over a weekly window against the launch reference, fired at 0.2.

Published per receipts rule 4: the precision at this prevalence, the resolution
floor of the sample, and the sample a stronger claim would need, printed next
to the action the policy takes (a retrain).
"""

from __future__ import annotations

import json
import math

import numpy as np
from common import build, write
from scipy import stats

from blind_window.detectors.input_side import psi
from blind_window.simulate.stream import generate

N_PERIODS = 240
N_HARM = 24  # 10% prevalence of true regressions
HARM_WITH_SHIFT = 12  # half of real regressions also move the covariates
N_HARMLESS_SHIFT = 48  # 20% of periods: covariates move, accuracy does not
PERIOD_DAYS = 30.0
RATE = 400.0
ONSET = 12.0
BASE_SEED = 500


def _alarm(stream) -> bool:
    ref = stream.features[stream.ts_day < 10.0]
    win = stream.features[(stream.ts_day >= stream.scenario.horizon_days - 7.0)]
    worst = max(psi(ref[:, j], win[:, j]).score for j in range(stream.features.shape[1]))
    return worst >= 0.2


def run() -> dict:
    kinds = (
        ["harm_with_shift"] * HARM_WITH_SHIFT
        + ["harm_silent"] * (N_HARM - HARM_WITH_SHIFT)
        + ["harmless_shift"] * N_HARMLESS_SHIFT
        + ["clean"] * (N_PERIODS - N_HARM - N_HARMLESS_SHIFT)
    )
    alarms = {"harm_with_shift": 0, "harm_silent": 0, "harmless_shift": 0, "clean": 0}
    counts = {k: kinds.count(k) for k in alarms}
    for i, kind in enumerate(kinds):
        sc = build(
            f"e4_{kind}_{i}",
            seed=BASE_SEED + i,
            horizon=PERIOD_DAYS,
            rate=RATE,
            median_delay=21.0,
            input_mag=1.0 if kind in ("harm_with_shift", "harmless_shift") else 0.0,
            input_onset=ONSET if kind in ("harm_with_shift", "harmless_shift") else None,
            drop_pts=4.0 if kind.startswith("harm") else 0.0,
            concept_onset=ONSET if kind.startswith("harm") else None,
        )
        if _alarm(generate(sc)):
            alarms[kind] += 1

    fired_total = sum(alarms.values())
    fired_on_harm = alarms["harm_with_shift"] + alarms["harm_silent"]
    precision = fired_on_harm / fired_total if fired_total else float("nan")
    recall = fired_on_harm / N_HARM
    # Resolution floors (rule 4): a zero is "below one in n", via the exact
    # Clopper-Pearson upper bound at 95%.
    silent_fired = alarms["harm_silent"]
    silent_n = counts["harm_silent"]
    silent_upper = float(stats.beta.ppf(0.95, silent_fired + 1, silent_n - silent_fired)) \
        if silent_fired < silent_n else 1.0
    clean_fired = alarms["clean"]
    clean_n = counts["clean"]
    clean_upper = float(stats.beta.ppf(0.95, clean_fired + 1, clean_n - clean_fired)) \
        if clean_fired < clean_n else 1.0
    # Sample a stronger claim would need: to certify silent-harm alarm rate
    # above 50% (i.e. the alarm usually catches a silent regression) you would
    # need at least this many silent-harm periods even if every one alarmed.
    n_for_half = math.ceil(math.log(0.05) / math.log(0.5))

    payload = {
        "design": {
            "n_periods": N_PERIODS,
            "prevalence_true_regression_pct": 100.0 * N_HARM / N_PERIODS,
            "share_of_regressions_also_shifting_inputs": HARM_WITH_SHIFT / N_HARM,
            "alarm": "worst-feature PSI >= 0.2, weekly window vs launch reference",
        },
        "measurements": {
            "alarms_total": fired_total,
            "alarms_on_real_regressions": fired_on_harm,
            "alarm_precision_pct": 100.0 * precision,
            "alarm_recall_on_regressions_pct": 100.0 * recall,
            "alarms_by_kind": alarms,
            "periods_by_kind": counts,
            "silent_harm_alarm_rate_upper_pct": 100.0 * silent_upper,
            "clean_false_alarm_rate_upper_pct": 100.0 * clean_upper,
            "periods_needed_to_certify_half_catch": n_for_half,
        },
    }
    write("e4_alarm_precision.json", payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run()["measurements"], indent=2))
