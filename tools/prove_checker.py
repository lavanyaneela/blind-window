"""Prove the checker catches a lie: break one figure, expect the build to fail.

A checker nobody has seen fail is a checker nobody should believe. For the
target metric, every anchor that actually matches a document is perturbed in a
scratch copy (one at a time), and check_numbers must fail on each. Trying only
the first anchor would leave the others unproven, which is how a previous
repository shipped a checker blind to half its own patterns.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_METRIC = "blind_window_predictions"
NUMBER_SLOT = r"(-?\d[\d,]*(?:\.\d+)?)"


def anchor_regex(template: str) -> re.Pattern:
    parts = [re.escape(p) for p in template.split("{}")]
    return re.compile(NUMBER_SLOT.join(parts))


def main() -> int:
    payload = json.loads((ROOT / "docs" / "metrics.json").read_text())
    anchors = payload["anchors"][TARGET_METRIC]
    docs = payload["checked_documents"]
    proved = 0
    for template in anchors:
        rx = anchor_regex(template)
        hit_doc = None
        for rel in docs:
            if rx.search((ROOT / rel).read_text()):
                hit_doc = rel
                break
        if hit_doc is None:
            continue
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "repo"
            shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(
                ".git", "runs", "mlruns", "__pycache__", ".venv", "node_modules"))
            doc = work / hit_doc
            text = doc.read_text()
            broken = rx.sub(lambda m: m.group(0).replace(m.group(1), "999888"), text, count=1)
            doc.write_text(broken)
            res = subprocess.run(
                [sys.executable, str(work / "tools" / "check_numbers.py")],
                cwd=work, capture_output=True, text=True,
            )
            if res.returncode == 0:
                print(f"FAIL: checker accepted a broken {template!r} in {hit_doc}")
                return 1
            proved += 1
            print(f"proved: breaking {template!r} in {hit_doc} fails the build")
    if proved == 0:
        print(f"FAIL: no anchor of {TARGET_METRIC} matches any document; nothing was proved")
        return 1
    print(f"checker proved against {proved} matching anchor(s) of {TARGET_METRIC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
