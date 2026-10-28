# ADR-004: the retraining trigger, priced

Status: accepted

## Context

Three triggers compete for the default: retrain when the input alarm fires,
retrain on a schedule, retrain when a regression is label-confirmed. E5 priced
them on identical streams over a 100 day horizon, in the two units an operator
pays: predictions served while degraded, and retrains fired with nothing to
fix. Every policy was granted a best-case retrain (the model realigns with the
current concept on the retrain day), so the measured differences belong to the
triggers alone. Three further grants are stated here because each flatters a
policy this ADR judges: the label-confirmed policy was handed the true onset
as its hypothesis; the drift policy's alarm latches after one retrain, since
its reference-window comparison would otherwise re-fire daily against a
persisting shift and bill the same alarm every day; and the schedule was run
at a cadence chosen in round numbers rather than tuned against it.

## Decision

**Label-confirmed is the default trigger, with eyes open about what it costs.**

The measured table (README, E5 section) is uncomfortable for this choice and
the choice survives it:

- The drift trigger is disqualified, not outscored. Its exposure total looks
  comparable inside the horizon, but it **leaves 15 of** the **30 real
  regressions** serving past the horizon, because a pure concept shift moves no
  covariate. Its exposure is unbounded in the quantity that matters; the
  in-horizon number understates a policy that never fixes half the incidents.
- The schedule beats label-confirmed on in-horizon exposure by brute force, at
  **150 wasted retrains**. The exchange rate is the decision variable:
  **1,305 degraded predictions avoided** per wasted retrain. Where a retrain is
  cheap (a nightly job) and a degraded prediction is expensive, buy the
  schedule; where a retrain carries review, validation and rollout cost, the
  schedule is paying full freight for mostly-empty fixes. A default must not
  assume retrains are free, so the default does not.
- Label-confirmed is the only trigger whose action is justified by evidence at
  the moment it acts: zero wasted retrains, every regression fixed. Its tax is
  the blind window itself, which this repository measures rather than hides.

The honest hybrid is stated as operational guidance, not implemented: run
label-confirmed as the decision gate, and if the computed exchange rate beats
your retrain cost, add a scheduled floor. The hybrid is not a fourth policy in
E5 because its cost curve is just the two published curves glued at a
site-specific price.

## Consequences

- The CLI's exit code 0 is the trigger: "regression confirmed" is the signal a
  label-confirmed retrain consumes. Exit code 2 is the tax notice.
- The registry records which trigger caused each version, so a quarter of
  operations can be audited in the same units E5 uses.
- If the simulator ever gains regressions that also move covariates by default,
  the drift trigger's numbers improve and this ADR must be re-run; the grid
  already contains that case at half weight, which is where its measured recall
  comes from.
