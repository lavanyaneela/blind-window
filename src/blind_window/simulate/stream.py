"""The seeded production stream, with ground truth attached.

The simulator exists because no public monitoring dataset lets input drift and
performance loss be injected independently, and independence is the property
every experiment here leans on. An input_shift moves the covariate mean along a
direction orthogonal to the concept, so detectors see it and accuracy does not.
A concept_shift rotates the concept away from the deployed model, so accuracy
sees it and the covariate distribution does not. Ground truth for both is
recorded in the stream metadata, including the realized (not requested)
accuracy drop, measured on a seeded calibration sample.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from blind_window.scenario import Scenario, ScenarioError

CONCEPT_STEEPNESS = 2.0
CALIBRATION_N = 200_000


def _sigmoid(z: np.ndarray) -> np.ndarray:
    out = np.empty_like(z, dtype=float)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n == 0:
        raise ScenarioError("cannot normalise a zero vector")
    return v / n


@dataclass(frozen=True)
class Geometry:
    """Three mutually orthogonal unit directions.

    w: the concept and the deployed model. v: the harmless shift direction,
    concentrated on the first features so the monitored marginals move. u: the
    rotation target for concept_shift. Orthogonality is what makes the two
    injections independent, so it is asserted, not assumed.
    """

    w: np.ndarray
    v: np.ndarray
    u: np.ndarray

    @staticmethod
    def build(n_features: int) -> "Geometry":
        w = _unit(np.ones(n_features))
        v_raw = np.zeros(n_features)
        v_raw[0] = 2.0
        v_raw[1] = 1.0
        v_raw[min(2, n_features - 1)] += 0.5
        v = _unit(v_raw - (v_raw @ w) * w)
        u_raw = np.zeros(n_features)
        u_raw[n_features - 1] = 1.0
        u_raw[n_features - 2] = -1.0
        u_raw = u_raw - (u_raw @ w) * w - (u_raw @ v) * v
        u = _unit(u_raw)
        for a, b in ((w, v), (w, u), (v, u)):
            if abs(float(a @ b)) > 1e-10:
                raise ScenarioError("geometry directions failed orthogonality")
        return Geometry(w=w, v=v, u=u)


def base_accuracy(seed: int) -> float:
    """Accuracy of the deployed model on its own concept, by seeded Monte Carlo."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 101]))
    z = rng.standard_normal(CALIBRATION_N)
    return float(np.mean(_sigmoid(CONCEPT_STEEPNESS * np.abs(z))))


def accuracy_at_angle(theta: float, seed: int) -> float:
    """Expected accuracy of the deployed model once the concept has rotated by
    theta, using common random numbers so the curve is smooth and seeded."""
    rng = np.random.default_rng(np.random.SeedSequence([seed, 102]))
    z1 = rng.standard_normal(CALIBRATION_N)
    z2 = rng.standard_normal(CALIBRATION_N)
    p_true = _sigmoid(CONCEPT_STEEPNESS * (np.cos(theta) * z1 + np.sin(theta) * z2))
    predicted_one = z1 >= 0
    p_correct = np.where(predicted_one, p_true, 1.0 - p_true)
    return float(np.mean(p_correct))


def angle_for_drop(drop_points: float, seed: int) -> tuple[float, float]:
    """Bisect the rotation angle that costs drop_points of accuracy.

    Returns (theta, realized_drop_points). The realized drop is what the
    calibration sample supports, and it is the number the stream records as
    ground truth. The requested drop is a target, never a published figure.
    """
    if drop_points <= 0:
        return 0.0, 0.0
    a0 = base_accuracy(seed)
    target = a0 - drop_points / 100.0
    floor = accuracy_at_angle(np.pi / 2, seed)
    if target < floor:
        raise ScenarioError(
            f"requested drop of {drop_points} points exceeds what rotation can cost "
            f"({(a0 - floor) * 100:.2f} points)"
        )
    lo, hi = 0.0, float(np.pi / 2)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if accuracy_at_angle(mid, seed) > target:
            lo = mid
        else:
            hi = mid
    theta = 0.5 * (lo + hi)
    return theta, (a0 - accuracy_at_angle(theta, seed)) * 100.0


@dataclass
class Stream:
    """Column arrays for one simulated horizon, plus ground truth metadata."""

    scenario: Scenario
    request_id: np.ndarray
    ts_day: np.ndarray
    features: np.ndarray
    score: np.ndarray
    predicted: np.ndarray
    y_true: np.ndarray
    label_day: np.ndarray
    meta: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return int(self.request_id.shape[0])


def _draw_delays(sc: Scenario, rng: np.random.Generator, hardness: np.ndarray) -> np.ndarray:
    d = sc.delay
    n = hardness.shape[0]
    if d.kind == "fixed":
        base = np.full(n, d.median_days)
    elif d.kind == "lognormal":
        base = rng.lognormal(mean=np.log(max(d.median_days, 1e-9)), sigma=d.sigma, size=n)
    elif d.kind == "gamma":
        # shape chosen so the coefficient of variation matches sigma; scale fits the median
        shape = 1.0 / (d.sigma**2)
        raw = rng.gamma(shape=shape, scale=1.0, size=n)
        base = raw * (d.median_days / max(np.median(raw), 1e-9))
    else:  # pragma: no cover - ScenarioError guards this upstream
        raise ScenarioError(f"unknown delay kind {d.kind!r}")
    if d.coupling == "hard_cases_slower" and d.coupling_strength > 0:
        # Hard cases (concept probability near one half) wait longer for a label.
        # Centred so the coupling changes the composition of early labels, not
        # primarily the overall median.
        base = base * np.exp(d.coupling_strength * (hardness - float(np.mean(hardness))))
    return base


def generate(sc: Scenario) -> Stream:
    """Produce the full stream for a scenario, deterministically from its seed."""
    sc.validate()
    geo = Geometry.build(sc.n_features)
    rng = np.random.default_rng(np.random.SeedSequence([sc.seed, 1]))

    input_events = [d for d in sc.drifts if d.kind == "input_shift"]
    concept_events = [d for d in sc.drifts if d.kind == "concept_shift"]
    if len(input_events) > 1 or len(concept_events) > 1:
        raise ScenarioError("at most one drift event of each kind per scenario")

    theta = 0.0
    realized_drop = 0.0
    if concept_events:
        theta, realized_drop = angle_for_drop(concept_events[0].magnitude, sc.seed)

    days = int(np.ceil(sc.horizon_days))
    counts = rng.poisson(lam=sc.rate_per_day, size=days)
    n_total = int(counts.sum())

    ts = np.concatenate(
        [d + np.sort(rng.random(c)) for d, c in enumerate(counts)]
    ) if n_total else np.empty(0)
    ts = ts[ts < sc.horizon_days]
    n = ts.shape[0]

    x = rng.standard_normal((n, sc.n_features))
    if input_events:
        ev = input_events[0]
        shifted = ts >= ev.onset_day
        x[shifted] += ev.magnitude * geo.v

    z_model = x @ geo.w
    score = _sigmoid(CONCEPT_STEEPNESS * z_model)
    predicted = (score >= 0.5).astype(np.int8)

    w_eff = np.where(
        (ts >= concept_events[0].onset_day) if concept_events else np.zeros(n, dtype=bool),
        1.0,
        0.0,
    )
    z_true = np.where(
        w_eff > 0,
        np.cos(theta) * z_model + np.sin(theta) * (x @ geo.u),
        z_model,
    )
    p_true = _sigmoid(CONCEPT_STEEPNESS * z_true)
    y = (rng.random(n) < p_true).astype(np.int8)

    hardness = 1.0 - 2.0 * np.abs(p_true - 0.5)
    delays = _draw_delays(sc, rng, hardness)
    label_day = ts + delays

    meta = {
        "name": sc.name,
        "seed": sc.seed,
        "n_predictions": int(n),
        "base_accuracy": base_accuracy(sc.seed),
        "concept_onset_day": concept_events[0].onset_day if concept_events else None,
        "concept_theta": theta,
        "realized_drop_points": realized_drop,
        "input_onset_day": input_events[0].onset_day if input_events else None,
        "input_magnitude": input_events[0].magnitude if input_events else 0.0,
        "delay_median_days_configured": sc.delay.median_days,
        "delay_median_days_realized": float(np.median(delays)) if n else 0.0,
    }
    return Stream(
        scenario=sc,
        request_id=np.arange(n, dtype=np.int64),
        ts_day=ts,
        features=x,
        score=score,
        predicted=predicted,
        y_true=y,
        label_day=label_day,
        meta=meta,
    )
