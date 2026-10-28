"""Run every experiment and print one line per headline figure.

This is the `make experiments` entrypoint and part of `make verify`: every
figure in the documents is re-measured from scratch here, so a stale number
cannot survive a clean clone.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import e1_drift_vs_harm  # noqa: E402
import e2_window_size  # noqa: E402
import e3_confirmable  # noqa: E402
import e4_alarm_precision  # noqa: E402
import e5_policy_cost  # noqa: E402


def main() -> int:
    for mod in (e1_drift_vs_harm, e2_window_size, e3_confirmable, e4_alarm_precision,
                e5_policy_cost):
        payload = mod.run()
        name = mod.__name__
        keys = list(payload["measurements"])[:3]
        brief = ", ".join(f"{k}={payload['measurements'][k]}" for k in keys)
        print(f"{name}: {brief}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
