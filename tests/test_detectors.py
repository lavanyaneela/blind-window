"""Detectors fire on what moves the covariates and stay quiet on what does not."""

import numpy as np
import pytest
from scipy import stats

from blind_window.detectors.input_side import (
    DetectorError,
    ks,
    mmd,
    psi,
    scan_features,
)
from blind_window.detectors.label_side import (
    LabelSideError,
    labeled_fraction,
    windowed_accuracy,
)


def _rng(seed=0):
    return np.random.default_rng(seed)


def test_psi_is_near_zero_for_two_samples_of_the_same_distribution():
    r = _rng(1)
    reading = psi(r.standard_normal(5000), r.standard_normal(5000))
    assert reading.score < 0.05 and not reading.fired


def test_psi_fires_on_a_one_sd_mean_shift():
    r = _rng(2)
    reading = psi(r.standard_normal(5000), r.standard_normal(5000) + 1.0)
    assert reading.fired and reading.score > 0.2


def test_psi_matches_a_hand_computed_two_bin_case():
    # Reference 50/50 around its median; window 90/10. With ten reference
    # deciles each holding 10%, a window concentrated below the median puts
    # about 18% in each low bin and 2% in each high bin:
    # psi ~ 10 * mean contribution; compute exactly against the formula.
    reference = np.concatenate([np.zeros(500), np.ones(500)]) + _rng(3).random(1000) * 0.01
    window = np.concatenate([np.zeros(900), np.ones(100)]) + _rng(4).random(1000) * 0.01
    reading = psi(reference, window)
    expected = 5 * ((0.18 - 0.10) * np.log(0.18 / 0.10)) + 5 * (
        (0.02 - 0.10) * np.log(0.02 / 0.10)
    )
    assert reading.score == pytest.approx(expected, rel=0.15)


def test_psi_requires_a_single_feature_column():
    r = _rng(5)
    with pytest.raises(DetectorError, match="one column"):
        psi(r.standard_normal((100, 2)), r.standard_normal((100, 2)))


def test_detectors_reject_samples_that_are_too_small():
    with pytest.raises(DetectorError, match="at least"):
        psi(np.ones(5), np.ones(5))


def test_ks_statistic_agrees_with_scipy():
    r = _rng(6)
    a, b = r.standard_normal(2000), r.standard_normal(2000) + 0.3
    reading = ks(a, b)
    assert reading.score == pytest.approx(stats.ks_2samp(a, b).statistic)


def test_ks_does_not_fire_on_identical_distributions():
    r = _rng(7)
    assert not ks(r.standard_normal(2000), r.standard_normal(2000)).fired


def test_mmd_does_not_fire_under_the_null():
    r = _rng(8)
    reading = mmd(r.standard_normal((1000, 4)), r.standard_normal((1000, 4)), _rng(9))
    assert not reading.fired


def test_mmd_fires_on_a_multivariate_shift():
    r = _rng(10)
    shifted = r.standard_normal((1000, 4)) + np.array([0.8, 0.8, 0.0, 0.0])
    reading = mmd(r.standard_normal((1000, 4)), shifted, _rng(11))
    assert reading.fired and reading.score > reading.threshold


def test_mmd_is_deterministic_given_the_same_rng_seed():
    r = _rng(12)
    ref, win = r.standard_normal((500, 3)), r.standard_normal((500, 3))
    a = mmd(ref, win, _rng(13)).score
    b = mmd(ref, win, _rng(13)).score
    assert a == b


def test_mmd_requires_the_feature_matrix_not_a_column():
    with pytest.raises(DetectorError, match="multivariate"):
        mmd(np.ones(100), np.ones(100), _rng(14))


def test_mmd_rejects_a_degenerate_constant_sample():
    with pytest.raises(DetectorError, match="degenerate"):
        mmd(np.ones((100, 2)), np.ones((100, 2)), _rng(15))


def test_scan_features_returns_the_three_standard_readings(shift_stream):
    pre = shift_stream.ts_day < 10
    out = scan_features(shift_stream.features[pre], shift_stream.features[~pre], _rng(16))
    assert set(out) == {"psi", "ks", "mmd"}
    assert out["psi"].fired  # the shift direction loads on monitored features


def test_windowed_accuracy_uses_only_labels_known_by_asof():
    ts = np.array([0.5, 1.5, 2.5])
    lab = np.array([1.0, 9.0, 3.0])
    correct = np.array([1, 0, 1], dtype=np.int8)
    w = windowed_accuracy(ts, lab, correct, 0, 3, asof_day=4)
    assert w.n_labeled == 2 and w.accuracy == 1.0  # the wrong one is still unlabeled


def test_windowed_accuracy_is_none_when_nothing_is_labeled_yet():
    ts = np.array([0.5])
    w = windowed_accuracy(ts, np.array([9.0]), np.array([1], dtype=np.int8), 0, 1, asof_day=1)
    assert w.n_labeled == 0 and w.accuracy is None


def test_windowed_accuracy_rejects_an_inverted_window():
    with pytest.raises(LabelSideError, match="after"):
        windowed_accuracy(np.array([1.0]), np.array([2.0]), np.array([1], dtype=np.int8), 5, 3, 6)


def test_windowed_accuracy_rejects_an_asof_before_the_window():
    with pytest.raises(LabelSideError, match="before the window"):
        windowed_accuracy(np.array([1.0]), np.array([2.0]), np.array([1], dtype=np.int8), 3, 5, 2)


def test_labeled_fraction_is_zero_when_nothing_was_served_after_onset():
    assert labeled_fraction(np.array([1.0]), np.array([2.0]), onset_day=5, asof_day=9) == 0.0


def test_labeled_fraction_counts_arrived_labels_only(harm_stream):
    s = harm_stream
    frac = labeled_fraction(s.ts_day, s.label_day, onset_day=10, asof_day=15)
    assert 0.0 < frac < 1.0
