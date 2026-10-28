"""Each trigger policy pays the cost its information allows, no less."""

import pytest

from blind_window.policy.retrain import (
    PolicyError,
    drift_triggered,
    label_confirmed,
    scheduled,
)
from blind_window.power import OperatingPoint


def test_drift_policy_never_fires_on_a_pure_concept_shift(harm_stream):
    out = drift_triggered(harm_stream)
    assert out.retrain_days == ()
    assert out.harm_end_day is None
    assert out.exposed_predictions > 0


def test_drift_policy_fires_once_on_a_covariate_shift_and_latches(shift_stream):
    out = drift_triggered(shift_stream)
    assert len(out.retrain_days) == 1
    assert out.retrain_days[0] >= 10


def test_a_drift_alarm_on_a_harmless_stream_is_a_wasted_retrain(shift_stream):
    assert drift_triggered(shift_stream).wasted_retrains == 1


def test_drift_policy_catches_harm_that_also_moves_the_inputs(both_stream):
    out = drift_triggered(both_stream)
    assert out.harm_end_day is not None
    assert out.exposed_predictions < 3000


def test_scheduled_policy_retrains_on_its_cadence_regardless(clean_stream):
    out = scheduled(clean_stream, 7.0)
    assert len(out.retrain_days) == 4
    assert out.wasted_retrains == 4  # no harm existed, so every one was waste


def test_scheduled_policy_ends_harm_at_the_first_post_onset_slot(harm_stream):
    out = scheduled(harm_stream, 7.0)
    assert out.harm_end_day == 14.0
    assert out.wasted_retrains == len(out.retrain_days) - 1


def test_label_confirmed_policy_waits_for_the_labels(harm_stream):
    out = label_confirmed(harm_stream, 4.0, OperatingPoint())
    assert out.harm_end_day is not None
    assert out.harm_end_day > 10.0  # it cannot act at onset; the window taxes it
    assert out.wasted_retrains == 0


def test_label_confirmed_policy_never_retrains_without_a_concept_onset(shift_stream):
    out = label_confirmed(shift_stream, 4.0, OperatingPoint())
    assert out.retrain_days == () and out.wasted_retrains == 0


def test_exposure_counts_predictions_between_onset_and_harm_end(harm_stream):
    out = label_confirmed(harm_stream, 4.0, OperatingPoint())
    import numpy as np
    manual = int(np.count_nonzero(
        (harm_stream.ts_day >= 10) & (harm_stream.ts_day < out.harm_end_day)))
    assert out.exposed_predictions == manual


def test_policies_reject_a_nonpositive_cadence(harm_stream):
    with pytest.raises(PolicyError):
        scheduled(harm_stream, 0)
    with pytest.raises(PolicyError):
        drift_triggered(harm_stream, check_every_days=-1)
    with pytest.raises(PolicyError):
        label_confirmed(harm_stream, 2.0, OperatingPoint(), check_every_days=0)


def test_drift_policy_needs_a_populated_reference_window():
    from blind_window.simulate.stream import generate
    from tests.conftest import make_scenario
    tiny = generate(make_scenario(name="tiny", rate_per_day=3, horizon_days=30))
    with pytest.raises(PolicyError, match="reference"):
        drift_triggered(tiny)


def test_the_three_policies_disagree_on_the_same_harm_stream(harm_stream):
    d = drift_triggered(harm_stream)
    s = scheduled(harm_stream, 7.0)
    c = label_confirmed(harm_stream, 4.0, OperatingPoint())
    assert d.exposed_predictions > c.exposed_predictions > s.exposed_predictions >= 0
