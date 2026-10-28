"""Re-measure every published figure and write docs/metrics.json.

Runs the test suite for the count and coverage (reading the machine readable
junit and coverage artifacts, never a parsed progress line), reads every
experiment JSON in docs/experiments/, derives the handful of composite values,
and renders each metric with its declared format. Nothing here is typed by
hand; the experiment files themselves are produced by `make experiments`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics_spec import CHECKED_DOCUMENTS, METRICS, render  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "docs" / "experiments"
OUT = ROOT / "docs" / "metrics.json"


def run_suite() -> tuple[int, float]:
    junit = ROOT / ".pytest-junit.xml"
    cov = ROOT / "coverage.json"
    cmd = [
        sys.executable, "-m", "pytest", "-q",
        f"--junitxml={junit}", "--cov=blind_window", "--cov-report=json",
    ]
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stdout[-4000:] + res.stderr[-2000:])
        raise SystemExit("test suite failed; metrics not collected")
    suite = ET.parse(junit).getroot()
    node = suite if suite.tag == "testsuite" else suite.find("testsuite")
    tests_total = int(node.attrib["tests"])
    coverage = json.loads(cov.read_text())["totals"]["percent_covered"]
    return tests_total, float(coverage)


def exp(name: str) -> dict:
    p = EXP / name
    if not p.exists():
        raise SystemExit(f"missing experiment output {p}; run `make experiments` first")
    return json.loads(p.read_text())


def main() -> int:
    tests_total, coverage = run_suite()
    e1 = exp("e1_drift_vs_harm.json")["measurements"]
    e2 = exp("e2_window_size.json")
    e3 = exp("e3_confirmable.json")["measurements"]
    e4 = exp("e4_alarm_precision.json")
    e5 = exp("e5_policy_cost.json")["measurements"]
    default_scenario = json.loads((ROOT / "fixtures/scenarios/default.json").read_text())
    n_default = count_default_predictions()
    sql_duck = sorted(p.name for p in (ROOT / "sql/duckdb").glob("*.sql"))
    sql_pg = sorted(p.name for p in (ROOT / "sql/postgres").glob("*.sql"))
    if sql_duck != sql_pg:
        raise SystemExit(f"dialect file sets differ: {sql_duck} vs {sql_pg}")

    exposed_sched = e5["scheduled_30d"]["exposed"]
    exposed_label = e5["label_confirmed"]["exposed"]
    wasted_sched = e5["scheduled_30d"]["wasted"]
    values: dict[str, float | int] = {
        "tests_total": tests_total,
        "coverage_line_pct": coverage,
        "label_delay_median_days": default_scenario["delay"]["median_days"],
        "default_rate_per_day": default_scenario["rate_per_day"],
        "target_drop_pts": 2.0,
        "n_predictions_default": n_default,
        "blind_window_days": e2["measurements"]["default_blind_days"],
        "blind_window_predictions": e2["measurements"]["default_blind_predictions"],
        "answerable_day": e2["measurements"]["default_answerable_day"],
        "rate_16x_window_ratio": e2["measurements"]["rate_16x_shrinks_window_by"],
        "mdd_day7_pts": e3["mdd_day7_pts"],
        "mdd_day30_pts": e3["mdd_day30_pts"],
        "early_label_bias_coupled_pts": e3["early_label_bias_coupled_pts"],
        "drift_perf_correlation": e1["pearson_r"],
        "max_psi_zero_harm": e1["max_psi_with_zero_harm"],
        "max_silent_drop_pts": e1["max_drop_with_zero_shift_pts"],
        "alarms_on_harmless": e1["alarms_on_harmless_streams"],
        "n_harmless_streams": e1["n_harmless_streams"],
        "alarms_on_silent_harm": e1["alarms_on_silent_harm_streams"],
        "n_silent_harm_streams": e1["n_silent_harm_streams"],
        "alarm_precision_pct": e4["measurements"]["alarm_precision_pct"],
        "alarm_recall_pct": e4["measurements"]["alarm_recall_on_regressions_pct"],
        "true_regression_prevalence_pct": e4["design"]["prevalence_true_regression_pct"],
        "silent_catch_upper_pct": e4["measurements"]["silent_harm_alarm_rate_upper_pct"],
        "e5_exposed_drift": e5["drift_triggered"]["exposed"],
        "e5_exposed_scheduled": exposed_sched,
        "e5_exposed_label": exposed_label,
        "e5_wasted_scheduled": wasted_sched,
        "e5_missed_drift": e5["drift_triggered"]["harm_missed_entirely"],
        "e5_n_harm": e5["n_harm_streams"],
        "e5_predictions_per_retrain": (exposed_label - exposed_sched) / max(wasted_sched, 1),
        "sql_queries_per_dialect": len(sql_duck),
    }
    missing = set(METRICS) - set(values)
    extra = set(values) - set(METRICS)
    if missing or extra:
        raise SystemExit(f"metric set mismatch: missing={sorted(missing)} extra={sorted(extra)}")
    payload = {
        "metrics": values,
        "rendered": {k: render(k, v) for k, v in values.items()},
        "anchors": {k: METRICS[k]["anchors"] for k in METRICS},
        "checked_documents": list(CHECKED_DOCUMENTS),
        "note": "every value produced by running the suite and the experiments; see tools/",
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"collected {len(values)} metrics -> {OUT.relative_to(ROOT)}")
    return 0


def count_default_predictions() -> int:
    from blind_window.scenario import Scenario
    from blind_window.simulate.stream import generate

    sc = Scenario.load(ROOT / "fixtures/scenarios/default.json")
    return len(generate(sc))


if __name__ == "__main__":
    sys.exit(main())
