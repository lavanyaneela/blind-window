"""The power arithmetic: what is confirmable, when, and the refusal contract."""

import numpy as np
import pytest

from blind_window.power import (
    OperatingPoint,
    PowerError,
    blind_window,
    expected_labeled_by_day,
    judge,
    min_detectable_drop,
)


def test_alpha_outside_the_open_interval_is_rejected():
    with pytest.raises(PowerError, match="alpha"):
        OperatingPoint(alpha=0.6).validate()


def test_power_below_one_half_is_rejected():
    with pytest.raises(PowerError, match="power"):
        OperatingPoint(power=0.3).validate()


def test_more_post_labels_shrink_the_detectable_drop():
    op = OperatingPoint()
    drops = [min_detectable_drop(0.78, 20000, n, op) for n in (50, 500, 5000)]
    assert drops == sorted(drops, reverse=True)


def test_a_stricter_alpha_raises_the_detectable_drop():
    loose = min_detectable_drop(0.78, 20000, 500, OperatingPoint(alpha=0.1))
    strict = min_detectable_drop(0.78, 20000, 500, OperatingPoint(alpha=0.01))
    assert strict > loose


def test_an_empty_sample_is_refused_rather_than_sized():
    with pytest.raises(PowerError, match="non-empty"):
        min_detectable_drop(0.78, 0, 100, OperatingPoint())


def test_a_degenerate_baseline_accuracy_is_refused():
    with pytest.raises(PowerError, match="strictly inside"):
        min_detectable_drop(1.0, 100, 100, OperatingPoint())


def test_a_tiny_sample_cannot_confirm_anything_short_of_total_collapse():
    assert min_detectable_drop(0.78, 5, 2, OperatingPoint()) > 50.0


def test_expected_labeled_counts_only_post_onset_arrived_labels():
    ts = np.array([1.0, 5.0, 6.0, 7.0])
    lab = np.array([2.0, 9.0, 6.5, 20.0])
    assert expected_labeled_by_day(ts, lab, onset_day=5.0, asof_day=10.0) == 2


def test_the_blind_window_shrinks_when_labels_arrive_faster(harm_stream):
    s = harm_stream
    acc0 = float(np.mean((s.predicted == s.y_true)[s.ts_day < 10]))
    slow = blind_window(s.ts_day, s.ts_day + 12.0, 10, 30, acc0, 5.0, OperatingPoint())
    fast = blind_window(s.ts_day, s.ts_day + 1.0, 10, 30, acc0, 5.0, OperatingPoint())
    assert fast.blind_days < slow.blind_days


def test_predictions_in_window_counts_what_shipped_before_answerable(harm_stream):
    s = harm_stream
    acc0 = float(np.mean((s.predicted == s.y_true)[s.ts_day < 10]))
    bw = blind_window(s.ts_day, s.ts_day + 1.0, 10, 30, acc0, 5.0, OperatingPoint())
    assert bw.answerable_day is not None
    manual = int(np.count_nonzero((s.ts_day >= 10) & (s.ts_day < bw.answerable_day)))
    assert bw.predictions_in_window == manual


def test_a_window_never_answerable_runs_to_the_horizon(harm_stream):
    s = harm_stream
    acc0 = float(np.mean((s.predicted == s.y_true)[s.ts_day < 10]))
    bw = blind_window(s.ts_day, s.ts_day + 1000.0, 10, 30, acc0, 1.0, OperatingPoint())
    assert bw.answerable_day is None
    assert bw.blind_days == pytest.approx(20.0)


def test_the_target_drop_must_be_positive(harm_stream):
    s = harm_stream
    with pytest.raises(PowerError, match="positive"):
        blind_window(s.ts_day, s.label_day, 10, 30, 0.8, 0.0, OperatingPoint())


def test_the_horizon_must_extend_past_the_onset(harm_stream):
    s = harm_stream
    with pytest.raises(PowerError, match="horizon"):
        blind_window(s.ts_day, s.label_day, 10, 10, 0.8, 1.0, OperatingPoint())


def test_judge_refuses_with_exit_two_when_no_post_labels_exist():
    v = judge(np.ones(100, dtype=np.int8), np.ones(0, dtype=np.int8), 2.0, OperatingPoint())
    assert v.exit_code == 2 and "no post-onset labels" in v.detail


def test_judge_refuses_inside_the_blind_window():
    rng = np.random.default_rng(1)
    base = (rng.random(5000) < 0.8).astype(np.int8)
    post = (rng.random(20) < 0.7).astype(np.int8)
    v = judge(base, post, 2.0, OperatingPoint())
    assert v.exit_code == 2 and v.min_detectable_points > 2.0


def test_judge_confirms_a_real_drop_with_exit_zero():
    rng = np.random.default_rng(2)
    base = (rng.random(20000) < 0.80).astype(np.int8)
    post = (rng.random(20000) < 0.74).astype(np.int8)
    v = judge(base, post, 2.0, OperatingPoint())
    assert v.exit_code == 0 and v.p_value < 0.05 and v.observed_drop_points > 4.0


def test_judge_answers_no_with_exit_one_when_nothing_moved():
    rng = np.random.default_rng(3)
    base = (rng.random(20000) < 0.80).astype(np.int8)
    post = (rng.random(20000) < 0.80).astype(np.int8)
    assert judge(base, post, 2.0, OperatingPoint()).exit_code == 1


def test_judge_rejects_an_empty_baseline():
    with pytest.raises(PowerError, match="baseline"):
        judge(np.ones(0, dtype=np.int8), np.ones(10, dtype=np.int8), 2.0, OperatingPoint())


def test_judge_rejects_a_degenerate_baseline_of_all_correct():
    with pytest.raises(PowerError, match="degenerate"):
        judge(np.ones(100, dtype=np.int8), np.ones(5000, dtype=np.int8), 2.0, OperatingPoint())
