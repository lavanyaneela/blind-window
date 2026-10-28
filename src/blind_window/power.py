"""The core computation: what is confirmable, and when.

Given a label delay distribution, a traffic rate, and an operating point
(alpha, power), this module answers the only question the blind window allows:
the smallest accuracy drop that the labels available on day t could confirm.
Everything else in the repository is scaffolding around these functions.

The design is unpaired by construction. The baseline window and the post-onset
window score different requests, so the correct arithmetic is a two-sample
comparison of proportions, not the paired test a fixed evaluation suite would
need. ADR-003 carries the operating point argument; the censoring caveat (early
labels over-represent short-delay requests) is ADR-005 and experiment E3b.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


class PowerError(ValueError):
    """Raised when an operating point or sample is unusable."""


@dataclass(frozen=True)
class OperatingPoint:
    """Alpha and power for a one-sided test of accuracy decrease."""

    alpha: float = 0.05
    power: float = 0.80

    def validate(self) -> None:
        if not (0 < self.alpha < 0.5):
            raise PowerError("alpha must be in (0, 0.5)")
        if not (0.5 <= self.power < 1):
            raise PowerError("power must be in [0.5, 1)")


def min_detectable_drop(
    baseline_acc: float, n_baseline: int, n_post: int, op: OperatingPoint
) -> float:
    """Smallest accuracy drop (in points) detectable at the operating point.

    One-sided two-proportion normal approximation, solved for the drop by
    bisection. Returns the drop in percentage points. Raises when either sample
    is empty, because no arithmetic turns zero labels into a verdict.
    """
    op.validate()
    if n_baseline <= 0 or n_post <= 0:
        raise PowerError("both samples must be non-empty to size a detectable drop")
    if not (0 < baseline_acc < 1):
        raise PowerError("baseline accuracy must be strictly inside (0, 1)")
    z_a = float(stats.norm.ppf(1 - op.alpha))
    z_b = float(stats.norm.ppf(op.power))
    p0 = baseline_acc

    def achievable(drop: float) -> bool:
        p1 = p0 - drop
        if p1 <= 0:
            # Accuracy cannot fall below zero, so a drop of the full baseline
            # is always "detectable"; this is the cap the bisection converges
            # toward when the sample supports nothing smaller.
            return True
        se_null = np.sqrt(p0 * (1 - p0) * (1 / n_baseline + 1 / n_post))
        se_alt = np.sqrt(p0 * (1 - p0) / n_baseline + p1 * (1 - p1) / n_post)
        return drop >= z_a * se_null + z_b * se_alt

    lo, hi = 0.0, p0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if achievable(mid):
            hi = mid
        else:
            lo = mid
    return 100.0 * hi


def expected_labeled_by_day(
    ts_day: np.ndarray, label_day: np.ndarray, onset_day: float, asof_day: float
) -> int:
    """Count of post-onset predictions whose label has arrived by asof_day."""
    mask = (ts_day >= onset_day) & (label_day <= asof_day)
    return int(np.count_nonzero(mask))


@dataclass(frozen=True)
class BlindWindowResult:
    """The window during which a drop of target size cannot be confirmed."""

    target_drop_points: float
    blind_days: float
    answerable_day: float | None  # absolute day; None when never answerable in horizon
    predictions_in_window: int
    mdd_curve_days: tuple[float, ...]
    mdd_curve_points: tuple[float, ...]


def blind_window(
    ts_day: np.ndarray,
    label_day: np.ndarray,
    onset_day: float,
    horizon_day: float,
    baseline_acc: float,
    target_drop_points: float,
    op: OperatingPoint,
    grid_step_days: float = 0.5,
) -> BlindWindowResult:
    """Walk days after onset until the target drop becomes confirmable.

    Both samples mature as labels arrive: the baseline count on day t is the
    pre-onset predictions labeled by t, not the count frozen at onset. The
    blind window ends on the first day the minimum detectable drop falls to
    the target. predictions_in_window counts every prediction served before
    that day, which is the headline: the exposure no monitoring can shrink.
    """
    if target_drop_points <= 0:
        raise PowerError("target drop must be positive points of accuracy")
    if horizon_day <= onset_day:
        raise PowerError("horizon must extend past the onset")
    days = np.arange(onset_day + grid_step_days, horizon_day + 1e-9, grid_step_days)
    mdd = []
    answerable: float | None = None
    for d in days:
        n_post = expected_labeled_by_day(ts_day, label_day, onset_day, float(d))
        n_base = int(np.count_nonzero((ts_day < onset_day) & (label_day <= float(d))))
        if n_post == 0 or n_base == 0:
            mdd.append(float("inf"))
            continue
        m = min_detectable_drop(baseline_acc, n_base, n_post, op)
        mdd.append(m)
        if answerable is None and m <= target_drop_points:
            answerable = float(d)
    end = answerable if answerable is not None else float(horizon_day)
    served = int(np.count_nonzero((ts_day >= onset_day) & (ts_day < end)))
    return BlindWindowResult(
        target_drop_points=target_drop_points,
        blind_days=float(end - onset_day),
        answerable_day=answerable,
        predictions_in_window=served,
        mdd_curve_days=tuple(float(d - onset_day) for d in days),
        mdd_curve_points=tuple(float(m) for m in mdd),
    )


@dataclass(frozen=True)
class Verdict:
    """Outcome of asking the question on a given day. exit_code is the CLI contract."""

    exit_code: int
    n_post_labeled: int
    min_detectable_points: float
    observed_drop_points: float | None
    p_value: float | None
    detail: str


def judge(
    baseline_correct: np.ndarray,
    post_correct: np.ndarray,
    target_drop_points: float,
    op: OperatingPoint,
) -> Verdict:
    """Decide: confirmed drop (0), no drop at this confidence (1), or refuse (2).

    Refusal is the point of the tool. When the labels available today could not
    confirm even the target drop, any verdict would be noise wearing a badge,
    so the tool says "not yet knowable" instead of guessing.
    """
    op.validate()
    n_base = int(baseline_correct.shape[0])
    n_post = int(post_correct.shape[0])
    if n_base == 0:
        raise PowerError("baseline window has no labeled predictions")
    p0 = float(np.mean(baseline_correct))
    if n_post == 0:
        return Verdict(2, 0, 100.0 * p0, None, None, "no post-onset labels have arrived")
    if not (0 < p0 < 1):
        raise PowerError("baseline accuracy is degenerate (exactly 0 or 1)")
    mdd = min_detectable_drop(p0, n_base, n_post, op)
    if mdd > target_drop_points:
        return Verdict(
            2,
            n_post,
            mdd,
            None,
            None,
            "inside the blind window: the labeled sample cannot confirm the target drop",
        )
    p1 = float(np.mean(post_correct))
    drop = (p0 - p1) * 100.0
    # One-sided two-proportion z test, pooled variance under the null.
    pooled = (p0 * n_base + p1 * n_post) / (n_base + n_post)
    se = float(np.sqrt(pooled * (1 - pooled) * (1 / n_base + 1 / n_post)))
    if se == 0:
        raise PowerError("pooled standard error is zero; samples are degenerate")
    z = (p0 - p1) / se
    p_value = float(1 - stats.norm.cdf(z))
    if p_value < op.alpha:
        return Verdict(0, n_post, mdd, drop, p_value, "regression confirmed")
    return Verdict(1, n_post, mdd, drop, p_value, "no regression at this confidence")
