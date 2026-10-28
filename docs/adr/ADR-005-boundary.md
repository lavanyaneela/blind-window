# ADR-005: the boundary, label delay is itself censored

Status: accepted

## Context

Every number in this repository is conditioned on a known label delay
distribution. That is the one input production cannot hand you cleanly, and the
honest statement of why belongs in its own ADR, because it is the claim a
senior reviewer will probe first.

## The boundary, stated

**The delay distribution here is configured, not observed.** In production it
must be estimated, and the estimation problem is right-censored twice over:

- On any day, the labels you have are the fast ones. A label that has not
  arrived is indistinguishable from a label that never will (the user churned,
  the case was dropped, the outcome window lapsed). The observed latency
  deciles the tool prints therefore understate the true delay, and the SQL that
  computes them says so in its header.
- The censoring is not random. E3b couples delay to case difficulty and
  measures the result: the day 7 labeled accuracy for a post-onset cohort reads
  **11.93 points too high**, against a near-zero bias when delays are
  independent. Easy cases return first, and easy cases are the ones the model
  gets right. The early sample is a selection, not a preview, and no sample
  size repairs selection.

## What measuring this on real traffic would require

- A maturation model fit on cohorts old enough to be complete: for each
  prediction age, the share of eventually-arriving labels already in hand (the
  committed `maturity_curve` query is the data shape for this), plus a
  decision about the never-labeled mass, which is a survival-analysis problem
  with administrative censoring.
- A stability check that the delay distribution itself is stationary. A labeling
  backlog is a delay drift, and it poisons the blind window arithmetic exactly
  when operations are most stressed.
- For the difficulty coupling: either labels whose arrival process is
  documented, or an instrumented subsample with forced adjudication at a fixed
  age, which is the only way to measure the bias E3b injects.

## Consequences

- The tool's contract is conditional and the report prints the condition: the
  blind window is computed from the configured distribution, and the earliest
  answerable date inherits its optimism or pessimism.
- The first item of future work in the README (a survival estimator over
  partially arrived labels) is this ADR turned into a feature. Until it exists,
  the right production posture is to fit the maturation curve on completed
  cohorts and to treat the published windows as floors whenever the labeling
  pipeline is slower than its history.
