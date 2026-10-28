# ADR-001: a simulated stream rather than a public monitoring dataset

Status: accepted

## Context

Every claim in this repository compares what a monitor can see against what is
actually true. That requires ground truth for two different events: the moment
the input distribution moved, and the moment the model's accuracy dropped, each
with a known magnitude, and each injectable without the other.

No public monitoring dataset offers that. Datasets with real drift do not come
with a certificate of when the drift began, how large the performance cost was,
or whether the visible movement and the harm are the same event. Using one
would make E1 (does the alarm predict the harm) unfalsifiable: with no
independent injection there is no way to construct the corner cases, a visible
shift that costs nothing and an invisible shift that costs points.

## Decision

A seeded simulator with two orthogonal injections.

- **input_shift** moves the covariate mean along a direction orthogonal to the
  concept. The detectors see it; accuracy does not move, which the suite
  asserts.
- **concept_shift** rotates the concept away from the deployed model by an
  angle solved to cost a stated number of accuracy points on a seeded
  calibration sample. The covariate distribution is untouched, which the suite
  also asserts.

Orthogonality of the three directions (concept, shift, rotation target) is
asserted at construction, not assumed. The realized drop, measured on the
calibration sample, is recorded in the stream metadata; the requested drop is a
target and is never published.

Label delay is a distribution, not a constant, because the spread is what makes
the blind window a curve instead of a date. An optional coupling makes hard
cases wait longer for labels, which is the E3b censoring arm.

## Consequences

- Every figure is reproducible from a scenario JSON and a seed, offline.
- E1's correlation is a statement about a designed world where the two kinds of
  change occur independently. The README states this next to the number. The
  claim that transfers is the mechanism (the detectors consume covariates, the
  harm lives in the labels), not the magnitude.
- Realism is bounded: arrivals are Poisson by day, features are Gaussian, the
  deployed model is a fixed linear scorer. The power arithmetic consumes only
  correctness bits and timestamps, so none of those choices enter the headline
  computation.
