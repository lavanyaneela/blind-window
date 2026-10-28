"""The command line, and the exit code contract that is the project.

Four codes, and the distinction between them is the deliverable:
  0  regression confirmed at the stated confidence; magnitude and window printed
  1  no regression at the current confidence; the tool worked, the answer is no
  2  refused: inside the blind window; prints the earliest day the question
     becomes answerable and how many predictions ship before then
  3  the tool could not answer (bad input, broken store, internal error)

A broad except in main() is deliberate: without it a crash exits 1 and is
indistinguishable from "the answer is no". BLIND_WINDOW_DEBUG=1 re-raises.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

from blind_window.power import OperatingPoint, Verdict, blind_window, judge
from blind_window.scenario import Scenario
from blind_window.simulate.stream import generate
from blind_window.store.log_store import LogStore

EXIT_CONFIRMED = 0
EXIT_NO_REGRESSION = 1
EXIT_REFUSED = 2
EXIT_ERROR = 3


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="blind-window")
    sub = p.add_subparsers(dest="command", required=True)

    sim = sub.add_parser("simulate", help="generate a seeded stream into a duckdb log")
    sim.add_argument("--scenario", required=True, help="scenario json file")
    sim.add_argument("--db", required=True, help="duckdb file to create")
    sim.add_argument("--force", action="store_true", help="overwrite an existing db")

    for name in ("check", "report"):
        c = sub.add_parser(
            name,
            help="ask whether a regression is confirmable"
            if name == "check"
            else "full as-of report with the exposure table",
        )
        c.add_argument("--db", required=True)
        c.add_argument("--asof-day", type=float, required=True,
                       help="the day the question is asked; nothing after it is visible")
        c.add_argument("--drop", type=float, required=True,
                       help="target accuracy drop in points the operator needs to rule on")
        c.add_argument("--onset-day", type=float, default=None,
                       help="suspected onset; defaults to the stream's recorded onset")
        c.add_argument("--alpha", type=float, default=0.05)
        c.add_argument("--power", type=float, default=0.80)
        if name == "report":
            c.add_argument("--json", action="store_true", help="emit the report as json")
    return p


def _onset(store: LogStore, args: argparse.Namespace) -> float:
    if args.onset_day is not None:
        return float(args.onset_day)
    onset = store.meta_value("concept_onset_day")
    if onset is None:
        onset = store.meta_value("input_onset_day")
    if onset is None:
        raise ValueError("no onset recorded in the stream; pass --onset-day")
    return float(onset)


def _ask(store: LogStore, args: argparse.Namespace) -> tuple[Verdict, dict]:
    op = OperatingPoint(alpha=args.alpha, power=args.power)
    onset = _onset(store, args)
    if args.asof_day < onset:
        raise ValueError(f"asof day {args.asof_day} is before the onset {onset}")
    a = store.arrays()
    base = (a["ts_day"] < onset) & (a["label_day"] <= args.asof_day)
    post = (a["ts_day"] >= onset) & (a["label_day"] <= args.asof_day)
    v = judge(a["correct"][base], a["correct"][post], args.drop, op)
    ctx: dict = {"onset_day": onset, "asof_day": args.asof_day, "op": op, "arrays": a}
    if v.exit_code == EXIT_REFUSED:
        p0 = float(np.mean(a["correct"][base]))
        horizon = float(json.loads(store.meta_value("scenario_json"))["horizon_days"])
        bw = blind_window(a["ts_day"], a["label_day"], onset, horizon, p0, args.drop, op)
        ctx["blind"] = bw
    return v, ctx


def cmd_simulate(args: argparse.Namespace) -> int:
    db = Path(args.db)
    if db.exists():
        if not args.force:
            raise FileExistsError(f"{db} exists; pass --force to overwrite")
        db.unlink()
    db.parent.mkdir(parents=True, exist_ok=True)
    sc = Scenario.load(args.scenario)
    stream = generate(sc)
    store = LogStore(db)
    n = store.load_stream(stream)
    store.close()
    print(f"simulated {n} predictions over {sc.horizon_days:g} days into {db}")
    return 0 if n else EXIT_ERROR


def cmd_check(args: argparse.Namespace) -> int:
    store = LogStore(args.db)
    try:
        v, ctx = _ask(store, args)
        cols, rows = store.run("version_windows", {"asof": args.asof_day})
        at_risk = ", ".join(str(r[0]) for r in rows)
        if v.exit_code == EXIT_REFUSED:
            bw = ctx["blind"]
            when = (
                f"day {bw.answerable_day:g}"
                if bw.answerable_day is not None
                else "beyond the stream horizon"
            )
            print(
                f"REFUSED: inside the blind window for a {args.drop:g} point drop.\n"
                f"  labels arrived for {v.n_post_labeled} post-onset predictions; the smallest "
                f"confirmable drop today is {v.min_detectable_points:.2f} points.\n"
                f"  earliest answerable: {when}; predictions served before then: "
                f"{bw.predictions_in_window}.\n"
                f"  model version at risk: {at_risk}"
            )
        elif v.exit_code == EXIT_CONFIRMED:
            print(
                f"CONFIRMED: accuracy down {v.observed_drop_points:.2f} points "
                f"(p={v.p_value:.4f}, alpha={ctx['op'].alpha:g}) over "
                f"{v.n_post_labeled} labeled post-onset predictions.\n"
                f"  model version: {at_risk}"
            )
        else:
            print(
                f"NO REGRESSION at alpha={ctx['op'].alpha:g}: observed change "
                f"{v.observed_drop_points:.2f} points (p={v.p_value:.4f}) over "
                f"{v.n_post_labeled} labeled post-onset predictions."
            )
        return v.exit_code
    finally:
        store.close()


def cmd_report(args: argparse.Namespace) -> int:
    store = LogStore(args.db)
    try:
        v, ctx = _ask(store, args)
        onset = ctx["onset_day"]
        _, exposure = store.run("blind_exposure", {"onset": onset, "asof": args.asof_day})
        _, versions = store.run("version_windows", {"asof": args.asof_day})
        _, deciles = store.run("label_latency_deciles", {"asof": args.asof_day})
        payload = {
            "asof_day": args.asof_day,
            "onset_day": onset,
            "target_drop_points": args.drop,
            "verdict": {
                "exit_code": v.exit_code,
                "detail": v.detail,
                "n_post_labeled": v.n_post_labeled,
                "min_detectable_points": v.min_detectable_points,
                "observed_drop_points": v.observed_drop_points,
                "p_value": v.p_value,
            },
            "exposure": [
                {"day": r[0], "served": r[1], "labeled": r[2], "labeled_share": r[3]}
                for r in exposure
            ],
            "versions": [
                {"model_version": r[0], "served_from_day": r[1], "served_to_day": r[2],
                 "n_predictions": r[3], "n_labeled_asof": r[4], "labeled_share": r[5]}
                for r in versions
            ],
            "latency_deciles": [
                {"decile": r[0], "n": r[1], "median_delay_days": r[3]} for r in deciles
            ],
        }
        if v.exit_code == EXIT_REFUSED:
            bw = ctx["blind"]
            payload["blind_window"] = {
                "answerable_day": bw.answerable_day,
                "blind_days": bw.blind_days,
                "predictions_in_window": bw.predictions_in_window,
            }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"as of day {args.asof_day:g} (onset day {onset:g}): {v.detail}")
            print(f"labeled post-onset: {v.n_post_labeled}; "
                  f"smallest confirmable drop: {v.min_detectable_points:.2f} points")
            print("day  served  labeled  share")
            for r in exposure:
                print(f"{r[0]:>4}  {r[1]:>6}  {r[2]:>7}  {r[3]:.3f}")
        return v.exit_code
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "simulate":
            return cmd_simulate(args)
        if args.command == "check":
            return cmd_check(args)
        return cmd_report(args)
    except Exception as exc:  # noqa: BLE001 - the contract: errors are code 3, never code 1
        if os.environ.get("BLIND_WINDOW_DEBUG") == "1":
            raise
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
