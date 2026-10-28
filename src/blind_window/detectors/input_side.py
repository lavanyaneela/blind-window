"""Input-side drift detectors: PSI, KS, and MMD.

These watch the only thing watchable at serving time, the covariates. The
repository's claim is not that they are bad detectors; it is that what they
detect (distribution movement) and what harms the product (accuracy loss) are
different quantities, and the stream can move one without the other. Each
detector returns a score and a fired flag against its conventional threshold,
so E4 can price the alarm at a realistic prevalence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

PSI_BINS = 10
PSI_FIRE_THRESHOLD = 0.2  # the conventional "significant shift" line
KS_ALPHA = 0.01
MMD_PERMUTATIONS = 1000  # the 0.99 null quantile needs tail mass behind it


class DetectorError(ValueError):
    """Raised when a detector is given an unusable sample."""


@dataclass(frozen=True)
class DetectorReading:
    name: str
    score: float
    threshold: float
    fired: bool


def _check(reference: np.ndarray, window: np.ndarray, min_n: int = 20) -> None:
    if reference.ndim != window.ndim:
        raise DetectorError("reference and window must have the same dimensionality")
    if reference.shape[0] < min_n or window.shape[0] < min_n:
        raise DetectorError(f"need at least {min_n} rows in each sample")


def psi(reference: np.ndarray, window: np.ndarray) -> DetectorReading:
    """Population stability index on one feature, deciles fit on the reference.

    Bin edges come from reference quantiles, and both tails are open, so every
    window value lands in a bin. Zero counts are floored at one half row, the
    standard continuity fix, and the floor is part of the score definition.
    """
    _check(reference, window)
    if reference.ndim != 1:
        raise DetectorError("psi is a per-feature statistic; pass one column")
    edges = np.quantile(reference, np.linspace(0, 1, PSI_BINS + 1)[1:-1])
    ref_counts = np.histogram(reference, bins=np.concatenate(([-np.inf], edges, [np.inf])))[0]
    win_counts = np.histogram(window, bins=np.concatenate(([-np.inf], edges, [np.inf])))[0]
    ref_frac = np.maximum(ref_counts, 0.5) / reference.shape[0]
    win_frac = np.maximum(win_counts, 0.5) / window.shape[0]
    score = float(np.sum((win_frac - ref_frac) * np.log(win_frac / ref_frac)))
    return DetectorReading("psi", score, PSI_FIRE_THRESHOLD, score >= PSI_FIRE_THRESHOLD)


def ks(reference: np.ndarray, window: np.ndarray) -> DetectorReading:
    """Two-sample Kolmogorov-Smirnov on one feature.

    The reading keeps one semantics across the battery: score is the statistic
    and threshold is the critical statistic at KS_ALPHA (asymptotic), so
    fired means score above threshold for all three detectors.
    """
    _check(reference, window)
    if reference.ndim != 1:
        raise DetectorError("ks is a per-feature statistic; pass one column")
    res = stats.ks_2samp(reference, window, method="asymp")
    n, m_ = reference.shape[0], window.shape[0]
    critical = float(np.sqrt(-np.log(KS_ALPHA / 2) / 2) * np.sqrt((n + m_) / (n * m_)))
    return DetectorReading("ks", float(res.statistic), critical, float(res.statistic) > critical)


def mmd(
    reference: np.ndarray,
    window: np.ndarray,
    rng: np.random.Generator,
    max_rows: int = 400,
) -> DetectorReading:
    """Multivariate maximum mean discrepancy with an RBF kernel.

    Bandwidth by the median heuristic on the pooled sample; the firing
    threshold is the 0.99 quantile of a permutation null with enough
    permutations that the quantile has tail mass behind it, so the score and
    its threshold come from the same data and the threshold's resolution is
    one part in the permutation count. Subsampling keeps the quadratic
    kernel affordable; the subsample is drawn from the caller's rng so a run
    is reproducible end to end.
    """
    _check(reference, window)
    if reference.ndim != 2:
        raise DetectorError("mmd is multivariate; pass the feature matrix")
    n_ref = min(max_rows, reference.shape[0])
    ref = reference[rng.choice(reference.shape[0], n_ref, replace=False)]
    win = window[rng.choice(window.shape[0], min(max_rows, window.shape[0]), replace=False)]
    pooled = np.vstack([ref, win])
    sq = np.sum(pooled**2, axis=1)
    d2 = sq[:, None] + sq[None, :] - 2 * (pooled @ pooled.T)
    np.fill_diagonal(d2, np.nan)
    med = float(np.nanmedian(d2))
    if med <= 0:
        raise DetectorError("median pairwise distance is zero; sample is degenerate")
    k = np.exp(-np.nan_to_num(d2, nan=0.0) / med)
    n1, n2 = ref.shape[0], win.shape[0]

    def mmd_stat(idx1: np.ndarray, idx2: np.ndarray) -> float:
        k11 = k[np.ix_(idx1, idx1)]
        k22 = k[np.ix_(idx2, idx2)]
        k12 = k[np.ix_(idx1, idx2)]
        a = (k11.sum() - np.trace(k11)) / (len(idx1) * (len(idx1) - 1))
        b = (k22.sum() - np.trace(k22)) / (len(idx2) * (len(idx2) - 1))
        return float(a + b - 2 * k12.mean())

    base_idx1 = np.arange(n1)
    base_idx2 = np.arange(n1, n1 + n2)
    observed = mmd_stat(base_idx1, base_idx2)
    null = np.empty(MMD_PERMUTATIONS)
    all_idx = np.arange(n1 + n2)
    for i in range(MMD_PERMUTATIONS):
        perm = rng.permutation(all_idx)
        null[i] = mmd_stat(perm[:n1], perm[n1:])
    threshold = float(np.quantile(null, 0.99))
    return DetectorReading("mmd", observed, threshold, observed > threshold)


def scan_features(
    reference: np.ndarray, window: np.ndarray, rng: np.random.Generator
) -> dict[str, DetectorReading]:
    """Run the standard battery: per-feature PSI and KS (worst feature kept),
    plus one multivariate MMD. Returns the readings keyed by detector name."""
    _check(reference, window)
    psi_best = max((psi(reference[:, j], window[:, j]) for j in range(reference.shape[1])),
                   key=lambda r: r.score)
    ks_best = max((ks(reference[:, j], window[:, j]) for j in range(reference.shape[1])),
                  key=lambda r: r.score)
    return {"psi": psi_best, "ks": ks_best, "mmd": mmd(reference, window, rng)}
