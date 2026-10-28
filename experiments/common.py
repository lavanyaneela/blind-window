"""Shared experiment plumbing: scenario builders and the output contract.

Every experiment writes one JSON file into docs/experiments/ containing only
measured values plus the configuration that produced them. collect_metrics.py
reads these files; nothing in a document is typed by hand. Seeds are fixed per
experiment so a fresh clone reproduces every figure bit for bit.
"""

from __future__ import annotations

import json
from pathlib import Path

from blind_window.scenario import Scenario

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "experiments"
DEFAULT_SCENARIO = Path(__file__).resolve().parents[1] / "fixtures" / "scenarios" / "default.json"


def build(
    name: str,
    seed: int,
    horizon: float,
    rate: float,
    median_delay: float,
    sigma: float = 0.8,
    input_mag: float = 0.0,
    input_onset: float | None = None,
    drop_pts: float = 0.0,
    concept_onset: float | None = None,
    coupling: str = "none",
    coupling_strength: float = 0.0,
) -> Scenario:
    drifts = []
    if input_mag > 0:
        drifts.append({"kind": "input_shift", "onset_day": input_onset, "magnitude": input_mag})
    if drop_pts > 0:
        drifts.append({"kind": "concept_shift", "onset_day": concept_onset, "magnitude": drop_pts})
    return Scenario.from_dict(
        {
            "name": name,
            "seed": seed,
            "horizon_days": horizon,
            "rate_per_day": rate,
            "n_features": 6,
            "delay": {
                "kind": "lognormal",
                "median_days": median_delay,
                "sigma": sigma,
                "coupling": coupling,
                "coupling_strength": coupling_strength,
            },
            "drifts": drifts,
        }
    )


def write(filename: str, payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / filename
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return out
