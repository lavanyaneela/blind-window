# blind-window: defense guide

Private preparation notes for the author. Everything here matches the committed
measurements; `tools/check_numbers.py` checks this file too.

## The one-breath summary

Production monitoring watches inputs because labels are late. This tool
computes what that lateness costs: on the default stream, a regression starting
day 30 is **blind for 20.5 days**, the operator's 2 point question is not
answerable **until day 50.5**, and the model serves **16,261 predictions
before** that date. The tool refuses to answer inside that window (exit code 2)
instead of guessing, and that refusal is the product.

## Why I built it this way

- **The stream is simulated** because the claims need ground truth for two
  separate events, the input moving and the accuracy dropping, injected
  independently. No public dataset certifies either. The simulator injects a
  covariate shift orthogonal to the concept (visible, harmless) and a concept
  rotation (invisible, harmful), and the suite asserts both independences.
- **The log is SQL** because monitoring state is two append-only event streams
  and every report is a time-windowed query. The six queries are committed as
  .sql files in two hand-written dialects, DuckDB for the offline default and
  PostgreSQL executed against a real server in a required CI job, row-for-row
  equal on the same fixture. There are **6 queries per dialect**: cumulative
  labeled counts, as-of windowed accuracy, latency deciles with NTILE, the
  exposure curve, version serving windows, and the cohort maturity curve with a
  cumulative window frame.
- **The verdict is unpaired** two-sample arithmetic: baseline and post-onset
  windows score different requests, unlike a fixed eval suite, which is paired.
  Power gates the right to answer (that gate is exit code 2), alpha gates the
  answer, defaults alpha 0.05 and power 0.80, both flags.
- **The registry is MLflow on SQLite** because a retraining policy means
  nothing without a record of which version served which window; versions
  carry serving-span and trigger tags, and E5 registers each of its
  label-confirmed retrains there. The refusal's version-at-risk line comes
  from the serving log's version_windows query, a deliberate complement.

## The numbers, and how each was measured

| Figure | Where it comes from |
| --- | --- |
| **blind for 20.5 days**, **16,261 predictions before** the verdict | E2 on the committed default scenario: walk the days after onset, recount both maturing labeled samples, find the first day the minimum detectable drop reaches the 2 point target |
| **9.93 points (day 7)**, **1.39 points (day 30)** | E3: the same walk read at fixed days; at day 1 there are no post-onset labels at all, so there is no number, which is the stronger statement |
| **correlation of -0.001** | E1: a grid varying input magnitude and concept drop independently, two seeds per cell; worst-feature PSI against realized drop |
| **PSI of 1.30** with zero harm, **losing 4.50 points** with zero shift | the two corners of the same grid |
| **precision of 20.0%**, **recall of 50.0%** at a **prevalence of 10%** | E4: periods at realistic base rates, half of real regressions also move covariates (the generous assumption); silent catch rate is only bounded, **below 22.1%**, because a measured zero is a resolution floor, not a zero |
| E5 totals and the **1,305 degraded predictions avoided** per wasted retrain | sixty streams, three policies on identical data, best-case retrains; the exchange rate is scheduled's exposure saving over label-confirmed divided by its **150 wasted retrains** |
| **147 tests**, **98.5% line coverage** | read from the junit and coverage JSON artifacts by the collector, never from a progress line |

## The war story to tell

The as-of accuracy SQL originally matched labels inside the CASE expression, so
unlabeled predictions fell to ELSE and counted as wrong. On the war-story
scenario the day-30 cohort, with **only 28 labels arrived**, was **reported
0.0518 accuracy** by the broken query, a **55.5 point phantom** gap below its
own labeled-only accuracy: the dashboard showed a collapse that was actually
label latency, the exact confusion the project exists to remove. I caught it
reading the first query output, fixed it to NULL-and-ignore, wrote a regression
test that recomputes every day from the raw arrays, and then a second test that
reconstructs the broken query and asserts the first test's check actually fails
against it, because a regression test that cannot fail proves nothing. The fix
is its own commit, and the three figures are re-measured on every verify.

One reconciliation to know cold: the fix commit's message, written in the
moment, prices the gap against the pre-onset baseline and eyeballs the cohort
size. The measured, receipts-guarded figures use the same cohort's own
labeled-only accuracy as the denominator, which is the honest comparison, and
the commit message stays as written because history here is never rewritten.
If a reviewer diffs the two, that is the answer: different denominator and a
rounder head-count, same bug, and the enforced numbers are the measured ones.

Second story if asked for another: with delay coupled to difficulty, day 7
accuracy reads **11.93 points too high**. Early labels are a selection, not a
sample. That one became ADR-005 and the survival-estimator item in future work.

## Release history, and why each version exists

- v0.1.0: the core could answer the question end to end: simulator, power
  arithmetic, SQL store, detectors, CLI with the four-code contract.
- v0.2.0: the answer became trustworthy: the full suite, the five experiments
  with committed measurements, and the receipts tooling that re-measures every
  published figure.
- v0.3.0: the answer became presentable and enforced: documents written against
  the anchors, evidence rendered byte-stable, CI with the required Postgres
  parity job and the prove-the-checker step.
- v1.0.0: the forensics pass, every finding fixed in its own commit; the
  contract frozen.

## Five likely interview questions

**1. Why does the tool refuse instead of reporting "no significant drop"?**
Because at low power "no significant drop" is vacuously true against any
realistic regression and reads as an acquittal. The refusal separates "the
answer is no" (exit code 1, issued only with power 0.80 against the target)
from "nobody can know yet" (exit code 2, with the earliest answerable date and
the exposure printed). Code 3 is reserved for the tool failing, so a crash can
never impersonate an acquittal.

**2. Your drift detector numbers look terrible. Are you saying drift detection
is useless?** No. I am saying the alarm and the harm are different quantities.
PSI watches covariates; the harmful injection moves none. At a **prevalence of
10%** the alarm's **precision of 20.0%** is mostly a fact about the base rate,
which is receipts rule four: precision is published at the prevalence the tool
will actually see, next to the action it would trigger. Input drift detection
earns its place for data-quality incidents; it cannot carry retraining
decisions alone, and E5 prices what happens when it does.

**3. Why a two-sample test and not a paired one?** Paired designs apply when
the same cases are scored before and after, like a fixed eval suite. A
production stream scores different requests in each window, so the information
lives in two independent proportions. Treating it as paired would overstate
sensitivity, in the flattering direction.

**4. The blind window assumes you know the delay distribution. You do not.**
Correct, and that is ADR-005. Observed latency is right-censored and the
censoring is not random: the E3b arm measures the day 7 labeled accuracy
reading **11.93 points too high** when delay couples to difficulty. In
production I would fit a maturation curve on completed cohorts (the committed
maturity query is the data shape) and treat published windows as floors. The
survival estimator is the first item of future work.

**5. Why is the Postgres job required when DuckDB answers everything?** Because
"a dialect exists" and "a dialect runs" are different claims. The parity job
executes all six Postgres queries against a real server on the same fixture and
asserts row equality with DuckDB, so the SQL skill on the resume is executed,
not asserted. The offline default stays DuckDB so `make verify` needs no
network.

## If the conversation goes deeper

- The minimum detectable drop is a bisection over the one-sided two-proportion
  normal approximation, both samples recounted as labels mature. Monotone in
  sample size and alpha, both pinned by tests.
- MMD exists in the battery for joint shifts with untouched marginals; its
  threshold is a permutation null, which is why it is not the default alarm.
- The exposure headline is counts, not milliseconds: counts are exact and
  machine independent, so the receipts can guard them. No wall-clock duration
  is published anywhere, and a sweep over every tracked markdown file enforces
  that.
