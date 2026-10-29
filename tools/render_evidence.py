"""Render the committed evidence from the default scenario, deterministically.

Two artifacts, both reproducible with this one script:
  docs/evidence/exposure-curve.svg  the served-vs-labeled curves with the blind
                                    window shaded, drawn from the same query the
                                    CLI report prints
  docs/evidence/report-day44.txt    the verbatim stdout of `blind-window report`
                                    on day 44, a refusal, which is the behaviour
                                    this repository exists to produce

The SVG is byte-stable across runs within one environment (fixed hash salt,
no creation date), so re-rendering locally leaves a clean tree. Across
environments matplotlib's glyph paths and ids differ at the same version, so
CI byte-diffs only the transcript and checks the SVG's content with
tools/check_svg_evidence.py.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.hashsalt"] = "blind-window"
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from blind_window.cli import main as cli_main  # noqa: E402
from blind_window.scenario import Scenario  # noqa: E402
from blind_window.simulate.stream import generate  # noqa: E402
from blind_window.store.log_store import LogStore  # noqa: E402

EVIDENCE = ROOT / "docs" / "evidence"
ASOF = 44.0
DROP = 2.0


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    db = ROOT / "runs" / "evidence.duckdb"
    db.parent.mkdir(exist_ok=True)
    if db.exists():
        db.unlink()
    sc = Scenario.load(ROOT / "fixtures/scenarios/default.json")
    store = LogStore(db)
    store.load_stream(generate(sc))
    onset = float(store.meta_value("concept_onset_day"))
    _, rows = store.run("blind_exposure", {"onset": onset, "asof": sc.horizon_days - 1})
    store.close()

    e2 = json.loads((ROOT / "docs/experiments/e2_window_size.json").read_text())
    answerable = e2["measurements"]["default_answerable_day"]

    days = [r[0] for r in rows]
    served = [r[1] for r in rows]
    labeled = [r[2] for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(days, served, label="predictions served since onset", linewidth=2)
    ax.plot(days, labeled, label="post-onset labels arrived", linewidth=2)
    ax.axvspan(onset, answerable, alpha=0.15, color="tab:red",
               label="blind window (2 pt question unanswerable)")
    ax.axvline(answerable, color="tab:red", linestyle=":", linewidth=1)
    ax.set_xlabel("day (simulated)")
    ax.set_ylabel("cumulative count")
    ax.set_title("The blind window: what ships before the question is answerable")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(EVIDENCE / "exposure-curve.svg", metadata={"Date": None})
    plt.close(fig)

    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli_main(["report", "--db", str(db), "--asof-day", str(ASOF),
                         "--drop", str(DROP)])
    header = (
        f"$ blind-window report --db {db.relative_to(ROOT)} "
        f"--asof-day {ASOF:g} --drop {DROP:g}\n"
    )
    footer = f"\n[exit code {code}]\n"
    (EVIDENCE / "report-day44.txt").write_text(header + buf.getvalue() + footer)
    print(f"evidence rendered: exit code {code} captured, svg written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
