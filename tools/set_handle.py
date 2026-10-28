"""Fill the GitHub handle placeholder and switch on the CI badge.

The repository ships with GITHUB_USERNAME everywhere a handle belongs, because
inventing a handle is inventing a fact about a person. The CI badge is inserted
only now: a badge pointing at a repository that does not exist renders
"unknown", which reads worse than no badge.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "GITHUB_USERNAME"
BADGE_MARK = "<!-- ci-badge: inserted by make set-handle -->"
HANDLE_RE = re.compile(r"^[A-Za-z\d](?:[A-Za-z\d]|-(?=[A-Za-z\d])){0,38}$")


def main(handle: str) -> int:
    if not HANDLE_RE.match(handle):
        print(f"error: {handle!r} is not a valid GitHub handle")
        return 1
    files = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    changed = 0
    for rel in files:
        p = ROOT / rel
        try:
            text = p.read_text()
        except (UnicodeDecodeError, IsADirectoryError):
            continue
        if PLACEHOLDER in text:
            p.write_text(text.replace(PLACEHOLDER, handle))
            changed += 1
    readme = ROOT / "README.md"
    text = readme.read_text()
    if BADGE_MARK in text:
        badge = (
            f"[![verify](https://github.com/{handle}/blind-window/actions/workflows/ci.yml/"
            f"badge.svg)](https://github.com/{handle}/blind-window/actions/workflows/ci.yml)"
        )
        text = text.replace(BADGE_MARK, badge)
        readme.write_text(text)
    print(f"handle set to {handle} in {changed} file(s); CI badge inserted")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python tools/set_handle.py <github-handle>")
        raise SystemExit(1)
    raise SystemExit(main(sys.argv[1]))
