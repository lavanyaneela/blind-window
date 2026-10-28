"""Shared fixtures. Streams are session scoped because generation dominates
suite time and every consumer treats them as read only."""

from __future__ import annotations

import pytest

from blind_window.scenario import Scenario
from blind_window.simulate.stream import Stream, generate


def make_scenario(**over) -> Scenario:
    raw = {
        "name": "test",
        "seed": 97,
        "horizon_days": 30,
        "rate_per_day": 200,
        "n_features": 6,
        "delay": {"kind": "lognormal", "median_days": 6, "sigma": 0.6},
        "drifts": [],
    }
    raw.update(over)
    return Scenario.from_dict(raw)


@pytest.fixture(scope="session")
def clean_stream() -> Stream:
    return generate(make_scenario(name="clean"))


@pytest.fixture(scope="session")
def harm_stream() -> Stream:
    return generate(
        make_scenario(
            name="harm",
            drifts=[{"kind": "concept_shift", "onset_day": 10, "magnitude": 6.0}],
        )
    )


@pytest.fixture(scope="session")
def shift_stream() -> Stream:
    return generate(
        make_scenario(
            name="shift",
            drifts=[{"kind": "input_shift", "onset_day": 10, "magnitude": 1.2}],
        )
    )


@pytest.fixture(scope="session")
def both_stream() -> Stream:
    return generate(
        make_scenario(
            name="both",
            drifts=[
                {"kind": "input_shift", "onset_day": 10, "magnitude": 1.2},
                {"kind": "concept_shift", "onset_day": 10, "magnitude": 6.0},
            ],
        )
    )
