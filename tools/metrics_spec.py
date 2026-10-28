"""The single declaration of every published figure: source, format, anchors.

One table, imported by collect_metrics.py (which measures) and
check_numbers.py (which enforces). A figure not in this table has no business
appearing in a document; the reverse check will flag it.

Fields per metric:
  source: where collect_metrics reads the raw value
  fmt: how the value renders in prose (the checker matches rendered strings)
  round: "nearest" | "floor". A minimum rounds down, never to nearest: a floor
         published as 0.990 under the words "never below" when the truth was
         0.98957 is a lie of one in the last digit.
  anchors: exact wordings a document must use, "{}" is the value slot. Short
         (four words or fewer) so they survive markdown line wrapping. Any one
         matching is enough.
"""

from __future__ import annotations

METRICS: dict[str, dict] = {
    # suite
    "tests_total": {
        "fmt": "{:d}", "round": "nearest", "anchors": ["{} tests"],
    },
    "coverage_line_pct": {
        "fmt": "{:.1f}", "round": "floor", "anchors": ["{}% line coverage"],
    },
    # default scenario configuration (declared inputs, still machine-read)
    "label_delay_median_days": {
        "fmt": "{:g}", "round": "nearest",
        "anchors": ["median delay {} days", "delay of {} days"],
    },
    "default_rate_per_day": {
        "fmt": "{:g}", "round": "nearest", "anchors": ["{} predictions per day"],
    },
    "target_drop_pts": {
        "fmt": "{:g}", "round": "nearest",
        "anchors": ["a {} point drop", "the {} point question", "{} point target"],
    },
    "n_predictions_default": {
        "fmt": "{:d}", "round": "nearest", "anchors": ["{} predictions over"],
    },
    # E2: the headline
    "blind_window_days": {
        "fmt": "{:g}", "round": "nearest",
        "anchors": ["blind for {} days", "{} days of blindness"],
    },
    "blind_window_predictions": {
        "fmt": "{:,d}", "round": "nearest",
        "anchors": ["{} predictions before", "serves {} predictions"],
    },
    "answerable_day": {
        "fmt": "{:g}", "round": "nearest", "anchors": ["until day {}", "answerable on day {}"],
    },
    "rate_16x_window_ratio": {
        "fmt": "{:.2f}", "round": "floor",
        "anchors": ["only {}x", "window by {}x"],
    },
    # E3
    "mdd_day7_pts": {
        "fmt": "{:.2f}", "round": "floor",
        "anchors": ["{} points (day 7)", "smaller than {} points"],
    },
    "mdd_day30_pts": {
        "fmt": "{:.2f}", "round": "floor", "anchors": ["{} points (day 30)"],
    },
    "early_label_bias_coupled_pts": {
        "fmt": "{:.2f}", "round": "nearest",
        "anchors": ["biased by {} points", "{} points too high"],
    },
    # E1
    "drift_perf_correlation": {
        "fmt": "{:.3f}", "round": "nearest", "anchors": ["correlation of {}"],
    },
    "max_psi_zero_harm": {
        "fmt": "{:.2f}", "round": "floor", "anchors": ["psi of {}", "PSI of {}"],
    },
    "max_silent_drop_pts": {
        "fmt": "{:.2f}", "round": "floor", "anchors": ["losing {} points"],
    },
    "alarms_on_harmless": {
        "fmt": "{:d}", "round": "nearest", "anchors": ["alarmed on {} of"],
    },
    "n_harmless_streams": {
        "fmt": "{:d}", "round": "nearest", "anchors": ["of {} harmless streams"],
    },
    "alarms_on_silent_harm": {
        "fmt": "{:d}", "round": "nearest", "anchors": ["{} alarms on the"],
    },
    "n_silent_harm_streams": {
        "fmt": "{:d}", "round": "nearest", "anchors": ["{} silently harmful streams"],
    },
    # E4
    "alarm_precision_pct": {
        "fmt": "{:.1f}", "round": "floor", "anchors": ["precision of {}%"],
    },
    "alarm_recall_pct": {
        "fmt": "{:.1f}", "round": "floor", "anchors": ["recall of {}%"],
    },
    "true_regression_prevalence_pct": {
        "fmt": "{:g}", "round": "nearest", "anchors": ["prevalence of {}%"],
    },
    "silent_catch_upper_pct": {
        "fmt": "{:.1f}", "round": "nearest", "anchors": ["below {}%"],
    },
    # E5
    "e5_exposed_drift": {
        "fmt": "{:,d}", "round": "nearest", "anchors": ["{} degraded predictions (drift"],
    },
    "e5_exposed_scheduled": {
        "fmt": "{:,d}", "round": "nearest", "anchors": ["{} degraded predictions (scheduled"],
    },
    "e5_exposed_label": {
        "fmt": "{:,d}", "round": "nearest", "anchors": ["{} degraded predictions (label"],
    },
    "e5_wasted_scheduled": {
        "fmt": "{:d}", "round": "nearest", "anchors": ["{} wasted retrains"],
    },
    "e5_missed_drift": {
        "fmt": "{:d}", "round": "nearest", "anchors": ["missed {} of", "leaves {} of"],
    },
    "e5_n_harm": {
        "fmt": "{:d}", "round": "nearest", "anchors": ["of {} real regressions"],
    },
    "e5_predictions_per_retrain": {
        "fmt": "{:,d}", "round": "floor", "anchors": ["{} degraded predictions avoided"],
    },
    # structure
    "sql_queries_per_dialect": {
        "fmt": "{:d}", "round": "nearest", "anchors": ["{} queries per dialect"],
    },
}

CHECKED_DOCUMENTS = (
    "README.md",
    "docs/defense-guide.md",
    "docs/adr/ADR-001-simulated-stream.md",
    "docs/adr/ADR-002-default-input-detector.md",
    "docs/adr/ADR-003-what-confirmed-means.md",
    "docs/adr/ADR-004-retraining-trigger.md",
    "docs/adr/ADR-005-boundary.md",
)

# Numbers allowed in prose that no metric re-measures. Each entry must appear
# in at least one checked document (an unused exemption is a stale exemption)
# and must not equal any rendered metric value (or it would hide staleness).
EXEMPT_NUMBERS = (
    "0.05",   # alpha, an operating point input stated in prose
    "0.80",   # power, same
    "0.2",    # the conventional PSI firing threshold
    "95",     # the coverage floor CI enforces, a policy not a measurement
    "100",    # the E5 horizon in days, a design input
    "0",      # exit code zero, referenced in prose next to its meaning
    "1",      # exit code one, same
    "3",      # exit code three, same
)


def render(name: str, value: float | int) -> str:
    spec = METRICS[name]
    fmt = spec["fmt"]
    if spec["round"] == "floor" and "f" in fmt:
        decimals = int(fmt.split(".")[1][0])
        scale = 10**decimals
        value = int(value * scale) / scale
    if fmt.endswith("d}"):
        value = int(round(value))
    return fmt.format(value)
