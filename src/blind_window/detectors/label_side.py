"""Label-side monitoring: accuracy over labels that have actually arrived.

The honest version of the metric every dashboard shows. The function is
as-of aware: on day t it sees only labels with arrival day <= t, grouped by
prediction day, so the curve it draws is the one an operator could really have
seen, not the one hindsight draws after every label lands.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class LabelSideError(ValueError):
    """Raised when a windowed metric is asked for an empty or invalid window."""


@dataclass(frozen=True)
class WindowedAccuracy:
    window_start_day: float
    window_end_day: float
    asof_day: float
    n_labeled: int
    accuracy: float | None  # None when nothing in the window is labeled yet


def windowed_accuracy(
    ts_day: np.ndarray,
    label_day: np.ndarray,
    correct: np.ndarray,
    window_start_day: float,
    window_end_day: float,
    asof_day: float,
) -> WindowedAccuracy:
    """Accuracy of predictions made in [start, end), using labels known by asof."""
    if window_end_day <= window_start_day:
        raise LabelSideError("window end must be after window start")
    if asof_day < window_start_day:
        raise LabelSideError("asof day is before the window opens")
    mask = (ts_day >= window_start_day) & (ts_day < window_end_day) & (label_day <= asof_day)
    n = int(np.count_nonzero(mask))
    acc = float(np.mean(correct[mask])) if n else None
    return WindowedAccuracy(window_start_day, window_end_day, asof_day, n, acc)


def labeled_fraction(
    ts_day: np.ndarray, label_day: np.ndarray, onset_day: float, asof_day: float
) -> float:
    """Share of post-onset predictions whose label has arrived by asof_day."""
    post = ts_day >= onset_day
    n_post = int(np.count_nonzero(post))
    if n_post == 0:
        return 0.0
    return float(np.count_nonzero(post & (label_day <= asof_day)) / n_post)
