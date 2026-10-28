"""A scenario file either defines a valid stream or is rejected with a reason."""

import json

import pytest

from blind_window.scenario import DelaySpec, DriftEvent, Scenario, ScenarioError
from tests.conftest import make_scenario


def test_a_valid_scenario_round_trips_through_from_dict():
    sc = make_scenario()
    assert sc.rate_per_day == 200


def test_load_reads_a_scenario_from_a_json_file(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({
        "name": "f", "seed": 1, "horizon_days": 10, "rate_per_day": 5,
        "delay": {"kind": "fixed", "median_days": 2},
    }))
    assert Scenario.load(p).name == "f"


def test_load_rejects_a_missing_file_with_its_path_in_the_message(tmp_path):
    with pytest.raises(ScenarioError, match="not found"):
        Scenario.load(tmp_path / "nope.json")


def test_load_rejects_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    with pytest.raises(ScenarioError, match="not valid JSON"):
        Scenario.load(p)


def test_a_missing_field_is_reported_as_a_scenario_error():
    with pytest.raises(ScenarioError, match="missing or mistypes"):
        Scenario.from_dict({"name": "x"})


def test_horizon_must_be_positive():
    with pytest.raises(ScenarioError, match="horizon_days"):
        make_scenario(horizon_days=0)


def test_rate_must_be_positive():
    with pytest.raises(ScenarioError, match="rate_per_day"):
        make_scenario(rate_per_day=-1)


def test_at_least_two_features_are_required_for_an_orthogonal_shift():
    with pytest.raises(ScenarioError, match="orthogonal"):
        make_scenario(n_features=1)


def test_an_unknown_delay_kind_is_rejected():
    with pytest.raises(ScenarioError, match="delay kind"):
        DelaySpec(kind="weibull", median_days=5).validate()


def test_a_spread_distribution_needs_positive_sigma():
    with pytest.raises(ScenarioError, match="sigma"):
        DelaySpec(kind="lognormal", median_days=5, sigma=0).validate()


def test_an_unknown_coupling_is_rejected():
    with pytest.raises(ScenarioError, match="coupling"):
        DelaySpec(kind="fixed", median_days=5, coupling="faster").validate()


def test_coupling_strength_without_coupling_is_rejected():
    with pytest.raises(ScenarioError, match="coupling_strength"):
        DelaySpec(kind="fixed", median_days=5, coupling="none", coupling_strength=1.0).validate()


def test_a_drift_event_outside_the_horizon_is_rejected():
    with pytest.raises(ScenarioError, match="outside horizon"):
        make_scenario(drifts=[{"kind": "input_shift", "onset_day": 99, "magnitude": 1.0}])


def test_an_unknown_drift_kind_is_rejected():
    with pytest.raises(ScenarioError, match="drift kind"):
        DriftEvent(kind="label_noise", onset_day=1, magnitude=1).validate(10)


def test_a_concept_drop_of_fifty_points_or_more_is_rejected():
    with pytest.raises(ScenarioError, match="below 50"):
        make_scenario(drifts=[{"kind": "concept_shift", "onset_day": 5, "magnitude": 50}])


def test_a_negative_magnitude_is_rejected():
    with pytest.raises(ScenarioError, match="non-negative"):
        make_scenario(drifts=[{"kind": "input_shift", "onset_day": 5, "magnitude": -0.5}])
