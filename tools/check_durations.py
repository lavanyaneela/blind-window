"""Enforce the no-wall-clock promise over every tracked file, not a shortlist.

The README promises that no wall-clock duration is published as a result:
milliseconds are a fact about the runner, and days here are simulated time, not
measured time. A promise about "anywhere in this repository" needs a check over
all tracked files (git ls-files, cached and others), because a new document is
otherwise invisible until it has already shipped.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DURATION = re.compile(
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:ms\b|msec|millisecond|microsecond|second(?!ary)|minute|hour)",
    re.IGNORECASE,
)
CHECK_SUFFIXES = {".md"}
# Lines allowed to mention a duration: each must say it is about the runner,
# not a result. The guard is fail-closed: an allowance must be used.
ALLOW_MARK = "(runner time, not a result)"


def tracked_markdown() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [ROOT / p for p in out if Path(p).suffix in CHECK_SUFFIXES]


def main() -> int:
    failures = []
    for path in tracked_markdown():
        text = path.read_text()
        text = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.DOTALL)
        for i, line in enumerate(text.splitlines(), start=1):
            if DURATION.search(line) and ALLOW_MARK not in line:
                failures.append(f"{path.relative_to(ROOT)}:{i}: wall-clock duration in prose")
    if failures:
        print(f"FAIL: {len(failures)} duration claim(s) outside code fences")
        for f in failures:
            print("  " + f)
        return 1
    print(f"durations clean across {len(tracked_markdown())} tracked markdown files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
