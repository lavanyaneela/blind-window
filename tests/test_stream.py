"""The simulator's two injections are independent, and everything is seeded."""

import numpy as np
import pytest

from blind_window.scenario import ScenarioError
from blind_window.simulate.stream import (
    Geometry,
    accuracy_at_angle,
    angle_for_drop,
    base_accuracy,
    generate,
)
from tests.conftest import make_scenario


def _acc(stream, mask) -> float:
    return float(np.mean((stream.predicted == stream.y_true)[mask]))


def test_the_same_scenario_generates_the_same_stream_bit_for_bit(clean_stream):
    again = generate(clean_stream.scenario)
    assert np.array_equal(clean_stream.y_true, again.y_true)
    assert np.array_equal(clean_stream.features, again.features)
    assert np.array_equal(clean_stream.label_day, again.label_day)


def test_geometry_directions_are_mutually_orthogonal_unit_vectors():
    g = Geometry.build(6)
    for v in (g.w, g.v, g.u):
        assert abs(np.linalg.norm(v) - 1.0) < 1e-12
    assert abs(g.w @ g.v) < 1e-10 and abs(g.w @ g.u) < 1e-10 and abs(g.v @ g.u) < 1e-10


def test_an_input_shift_does_not_change_accuracy(shift_stream, clean_stream):
    post = shift_stream.ts_day >= 10
    pre = ~post
    assert abs(_acc(shift_stream, post) - _acc(shift_stream, pre)) < 0.02


def test_an_input_shift_moves_the_covariate_mean(shift_stream):
    post = shift_stream.ts_day >= 10
    delta = shift_stream.features[post].mean(axis=0) - shift_stream.features[~post].mean(axis=0)
    assert float(np.linalg.norm(delta)) > 0.8


def test_a_concept_shift_drops_accuracy_near_the_requested_points(harm_stream):
    post = harm_stream.ts_day >= 10
    drop_pts = (_acc(harm_stream, ~post) - _acc(harm_stream, post)) * 100
    assert 3.5 < drop_pts < 9.0  # requested 6; a 4k row sample is allowed its noise


def test_a_concept_shift_leaves_the_covariate_distribution_untouched(harm_stream):
    post = harm_stream.ts_day >= 10
    delta = harm_stream.features[post].mean(axis=0) - harm_stream.features[~post].mean(axis=0)
    assert float(np.linalg.norm(delta)) < 0.1


def test_the_realized_drop_is_recorded_in_the_stream_metadata(harm_stream):
    assert abs(harm_stream.meta["realized_drop_points"] - 6.0) < 1e-6


def test_angle_for_drop_realizes_the_requested_drop_on_the_calibration_sample():
    theta, realized = angle_for_drop(4.0, seed=97)
    assert 0 < theta < np.pi / 2
    assert abs(realized - 4.0) < 1e-6


def test_angle_zero_is_returned_for_a_zero_drop():
    assert angle_for_drop(0.0, seed=97) == (0.0, 0.0)


def test_an_impossible_drop_is_rejected_with_the_achievable_maximum():
    with pytest.raises(ScenarioError, match="exceeds what rotation can cost"):
        angle_for_drop(45.0, seed=97)


def test_accuracy_at_angle_is_monotone_decreasing():
    a = [accuracy_at_angle(t, seed=97) for t in (0.0, 0.4, 0.8, 1.2)]
    assert a == sorted(a, reverse=True)


def test_base_accuracy_is_well_inside_the_open_interval():
    a0 = base_accuracy(97)
    assert 0.6 < a0 < 0.95


def test_two_drift_events_of_the_same_kind_are_rejected():
    sc = make_scenario(drifts=[
        {"kind": "input_shift", "onset_day": 5, "magnitude": 0.5},
        {"kind": "input_shift", "onset_day": 15, "magnitude": 0.5},
    ])
    with pytest.raises(ScenarioError, match="at most one"):
        generate(sc)


def test_fixed_delay_puts_every_label_exactly_median_days_later():
    s = generate(make_scenario(name="fixed", delay={"kind": "fixed", "median_days": 3}))
    assert np.allclose(s.label_day - s.ts_day, 3.0)


def test_gamma_delay_hits_the_configured_median():
    s = generate(make_scenario(name="g", delay={"kind": "gamma", "median_days": 5, "sigma": 0.5}))
    assert abs(float(np.median(s.label_day - s.ts_day)) - 5.0) < 0.5


def test_coupled_delay_makes_hard_cases_wait_longer():
    s = generate(make_scenario(
        name="c",
        delay={"kind": "lognormal", "median_days": 5, "sigma": 0.4,
               "coupling": "hard_cases_slower", "coupling_strength": 1.5},
    ))
    hardness = 1.0 - 2.0 * np.abs(s.score - 0.5)
    delays = s.label_day - s.ts_day
    hard = hardness > np.quantile(hardness, 0.8)
    easy = hardness < np.quantile(hardness, 0.2)
    assert float(np.median(delays[hard])) > float(np.median(delays[easy]))


def test_every_prediction_lands_inside_the_horizon(clean_stream):
    assert clean_stream.ts_day.max() < clean_stream.scenario.horizon_days
    assert clean_stream.ts_day.min() >= 0


def test_the_prediction_count_tracks_rate_times_horizon(clean_stream):
    expected = clean_stream.scenario.rate_per_day * clean_stream.scenario.horizon_days
    assert abs(len(clean_stream) - expected) / expected < 0.05
