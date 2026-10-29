"""Check the exposure-curve SVG semantically, not byte-wise.

The transcript (report-day44.txt) is measurement text and is byte-diffed in
CI. The SVG is a rendering: matplotlib's glyph paths and clip-path ids vary
between environments even at the same version, so a cross-machine byte-diff
is a flaky contract (the first real CI run proved it). What must hold
anywhere is the content: the file parses, it carries intrinsic dimensions,
and it contains the three elements the README's caption promises, the two
cumulative data lines and the shaded blind-window span. This script asserts
that for a given SVG, and CI runs it against both the committed file and a
fresh render.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG_NS = "{http://www.w3.org/2000/svg}"
MIN_PATHS = 20


def check(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        return [f"{path}: not well-formed XML: {exc}"]
    if not root.tag.endswith("svg"):
        problems.append(f"{path}: root element is {root.tag}, not svg")
    if not (root.get("width") and root.get("height")):
        problems.append(f"{path}: missing intrinsic width/height")
    text = path.read_text()
    paths = text.count("<path")
    if paths < MIN_PATHS:
        problems.append(f"{path}: only {paths} path elements; the plot is missing")
    if "opacity: 0.15" not in text:
        problems.append(f"{path}: the shaded blind-window span is missing")
    # The two data lines are the only stroked paths using the tab10 line colors.
    for color, name in (("#1f77b4", "served line"), ("#ff7f0e", "labeled line")):
        if color not in text:
            problems.append(f"{path}: {name} ({color}) is missing")
    return problems


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv] or [
        Path(__file__).resolve().parents[1] / "docs" / "evidence" / "exposure-curve.svg"
    ]
    failures: list[str] = []
    for t in targets:
        if not t.exists():
            failures.append(f"{t}: missing")
            continue
        failures.extend(check(t))
    if failures:
        print(f"FAIL: {len(failures)} svg evidence problem(s)")
        for f in failures:
            print("  " + f)
        return 1
    print(f"svg evidence checked: {len(targets)} file(s) carry the promised content")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
