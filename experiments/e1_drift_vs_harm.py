"""E1: does input drift predict performance loss?

A grid of streams where input shift magnitude and concept drop are varied
independently, including both corners: large visible shift with zero harm, and
real harm with zero visible shift. The grid design is stated with the result:
in a world where both kinds of change occur, the correlation below is how much
an input drift score tells you about accuracy loss. The corners are not edge
cases; they are constructible production weeks.
"""

from __future__ import annotations

import json

import numpy as np
from common import build, write
from scipy import stats

from blind_window.detectors.input_side import psi
from blind_window.simulate.stream import generate

INPUT_MAGS = (0.0, 0.25, 0.5, 1.0, 1.5)
DROPS_PTS = (0.0, 1.0, 2.0, 4.0)
SEEDS = (301, 302)
ONSET = 20.0
HORIZON = 60.0
RATE = 400.0
MEDIAN_DELAY = 10.0


def run() -> dict:
    rows = []
    for mi in INPUT_MAGS:
        for dc in DROPS_PTS:
            for seed in SEEDS:
                sc = build(
                    f"e1_m{mi}_d{dc}_s{seed}",
                    seed=seed,
                    horizon=HORIZON,
                    rate=RATE,
                    median_delay=MEDIAN_DELAY,
                    input_mag=mi,
                    input_onset=ONSET if mi > 0 else None,
                    drop_pts=dc,
                    concept_onset=ONSET if dc > 0 else None,
                )
                s = generate(sc)
                pre = s.ts_day < ONSET
                post = ~pre
                correct = s.predicted == s.y_true
                measured_drop = (
                    float(np.mean(correct[pre])) - float(np.mean(correct[post]))
                ) * 100.0
                worst_psi = max(
                    psi(s.features[pre][:, j], s.features[post][:, j]).score
                    for j in range(s.features.shape[1])
                )
                rows.append(
                    {
                        "input_mag": mi,
                        "requested_drop_pts": dc,
                        "seed": seed,
                        "worst_psi": worst_psi,
                        "measured_drop_pts": measured_drop,
                        "alarm_fired": worst_psi >= 0.2,
                    }
                )
    psis = np.array([r["worst_psi"] for r in rows])
    drops = np.array([r["measured_drop_pts"] for r in rows])
    pear = stats.pearsonr(psis, drops)
    spear = stats.spearmanr(psis, drops)
    harmless = [r for r in rows if r["requested_drop_pts"] == 0.0]
    silent = [r for r in rows if r["input_mag"] == 0.0 and r["requested_drop_pts"] > 0]
    payload = {
        "design": {
            "input_mags": INPUT_MAGS,
            "drops_pts": DROPS_PTS,
            "seeds": SEEDS,
            "n_streams": len(rows),
            "note": "axes varied independently by design; see README E1 framing",
        },
        "measurements": {
            "pearson_r": float(pear.statistic),
            "pearson_p": float(pear.pvalue),
            "spearman_r": float(spear.statistic),
            "max_psi_with_zero_harm": float(max(r["worst_psi"] for r in harmless)),
            "max_drop_with_zero_shift_pts": float(
                max(r["measured_drop_pts"] for r in silent)
            ),
            "alarms_on_harmless_streams": int(sum(r["alarm_fired"] for r in harmless)),
            "n_harmless_streams": len(harmless),
            "alarms_on_silent_harm_streams": int(sum(r["alarm_fired"] for r in silent)),
            "n_silent_harm_streams": len(silent),
        },
        "rows": rows,
    }
    write("e1_drift_vs_harm.json", payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run()["measurements"], indent=2))
