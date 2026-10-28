"""Fail the build when a document quotes a figure the code no longer produces.

Four passes, each one a scar from a previous repository in this series:

1. Anchor pass, per occurrence, over the FULL text of each checked document,
   fenced blocks and code spans included. Guarding only known-good lines closes
   mutation and leaves insertion wide open, so every occurrence of an anchor
   pattern anywhere must carry the current rendered value.
2. Containment pass: no two metrics may share an anchor template, including by
   substring, or one metric's prose silently validates against another's value.
3. Reverse pass: every bare number in prose (fences, code spans and HTML
   attributes excluded; ISO dates, version tags and ADR ids stripped first)
   must equal some rendered metric value or a declared exemption. A number
   nothing re-measures is a number that will go stale.
4. Exemption hygiene: every exemption is used at least once, and no exemption
   equals a rendered metric value (or it would hide staleness behind itself).

Exits nonzero on the first collected set of failures. Missing inputs fail
closed: a checker that returns 0 because its inputs were absent is worse than
no checker.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics_spec import EXEMPT_NUMBERS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
METRICS_JSON = ROOT / "docs" / "metrics.json"

NUMBER_SLOT = r"(-?\d[\d,]*(?:\.\d+)?)"
# Bare-number finder for the reverse pass: not preceded by word chars, dots,
# hyphens, slashes or colons (which would put us inside an identifier, a path,
# a sha fragment or a time), not followed by more word characters.
BARE_NUMBER = re.compile(r"(?<![\w./:\-])(-?\d[\d,]*(?:\.\d+)?)(?![\w])")
STRIP_PATTERNS = (
    re.compile(r"\d{4}-\d{2}-\d{2}"),  # ISO dates shed negative fragments otherwise
    re.compile(r"\bv\d+\.\d+\.\d+\b"),  # release tags
    re.compile(r"\bADR-\d+\b"),  # document ids
    re.compile(r"\bpostgres:\d+\b"),  # service container pins
    re.compile(r"\bPython 3\.\d+\b"),  # interpreter versions in prose
    re.compile(r"\b\d{1,2}:\d{2}\b"),  # clock times
)


def norm(s: str) -> str:
    return s.replace(",", "")


def strip_uncheckable(text: str) -> str:
    """Remove fenced blocks, inline code and HTML attributes for the reverse
    pass. Spans are replaced with placeholders of equal line structure so
    reported context stays readable."""
    text = re.sub(r"```.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]*`", "", text)
    text = re.sub(r"<[^>\n]+>", "", text)
    for pat in STRIP_PATTERNS:
        text = pat.sub("", text)
    return text


def anchor_regex(template: str) -> re.Pattern:
    parts = [re.escape(p) for p in template.split("{}")]
    return re.compile(NUMBER_SLOT.join(parts))


def main() -> int:
    if not METRICS_JSON.exists():
        print("FAIL: docs/metrics.json missing; run tools/collect_metrics.py first")
        return 1
    payload = json.loads(METRICS_JSON.read_text())
    rendered: dict[str, str] = payload["rendered"]
    anchors: dict[str, list[str]] = payload["anchors"]
    docs: list[str] = payload["checked_documents"]

    failures: list[str] = []

    # Pass 2 first: the spec itself must be sound before documents are judged.
    templates = [(m, a) for m, alist in anchors.items() for a in alist]
    for mi, ai in templates:
        for mj, aj in templates:
            if mi != mj and ai in aj:
                failures.append(
                    f"anchor containment: {mi!r} anchor {ai!r} is contained in {mj!r} anchor {aj!r}"
                )

    # Pass 4a: no exemption equals a rendered value.
    rendered_norms = {norm(v) for v in rendered.values()}
    for ex in EXEMPT_NUMBERS:
        if norm(ex) in rendered_norms:
            failures.append(f"exemption {ex!r} equals a rendered metric value; it would hide drift")

    matched_metrics: set[str] = set()
    exemptions_used: set[str] = set()

    for rel in docs:
        path = ROOT / rel
        if not path.exists():
            failures.append(f"checked document missing: {rel}")
            continue
        full = path.read_text()

        # Pass 1: anchors over the full text, every occurrence.
        covered: list[tuple[int, int]] = []
        for metric, alist in anchors.items():
            want = rendered[metric]
            for template in alist:
                for m in anchor_regex(template).finditer(full):
                    covered.append(m.span())
                    matched_metrics.add(metric)
                    if norm(m.group(1)) != norm(want):
                        failures.append(
                            f"{rel}: anchor {template!r} for {metric} carries "
                            f"{m.group(1)!r}, code produces {want!r}"
                        )

        # Pass 3: reverse scan on prose only.
        prose = strip_uncheckable(full)
        # Re-find anchor spans on the stripped prose so covered regions align.
        prose_covered: list[tuple[int, int]] = []
        for alist in anchors.values():
            for template in alist:
                for m in anchor_regex(template).finditer(prose):
                    prose_covered.append(m.span())
        for m in BARE_NUMBER.finditer(prose):
            if any(a <= m.start() and m.end() <= b for a, b in prose_covered):
                continue
            token = norm(m.group(1))
            if token in rendered_norms:
                continue
            if token in {norm(e) for e in EXEMPT_NUMBERS}:
                exemptions_used.add(token)
                continue
            line = prose.count("\n", 0, m.start()) + 1
            failures.append(
                f"{rel}:{line}: number {m.group(1)!r} matches no metric and no exemption"
            )

    # Pass 4b: every exemption used somewhere.
    unused = {norm(e) for e in EXEMPT_NUMBERS} - exemptions_used
    if unused:
        failures.append(f"unused exemptions (stale allow-list entries): {sorted(unused)}")

    unmatched = sorted(set(rendered) - matched_metrics)
    if unmatched:
        print(f"note: metrics with no anchored occurrence in any document: {unmatched}")

    if failures:
        print(f"FAIL: {len(failures)} receipts violation(s)")
        for f in failures:
            print("  " + f)
        return 1
    print(f"receipts clean: {len(matched_metrics)} metrics anchored across {len(docs)} documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
