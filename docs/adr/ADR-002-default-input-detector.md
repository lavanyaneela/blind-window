# ADR-002: PSI as the default input detector, and where it loses

Status: accepted

## Context

The tool ships three input-side detectors: per-feature PSI, per-feature KS, and
a multivariate MMD with a permutation threshold. One must be the default that
the drift-triggered policy and the E4 alarm use, because a policy that consults
three detectors with different firing semantics is really three policies.

## Decision

Worst-feature PSI at the conventional 0.2 threshold is the default.

Reasons, measured where stated:

- On this data shape (continuous features, mean shifts), PSI at 0.2 and KS at
  its critical statistic are expected to fire on the same streams; the suite
  checks each against the same null and asserts each fires on a one-sd
  mean shift, and nothing here measures their agreement across the full E1
  grid, so the same-streams claim is labelled an expectation. PSI's deciles are fit on the reference
  window once, so the production-side cost per check is a histogram, and its
  score is readable: practitioners already know what crossing 0.2 means.
- MMD is the only one that would catch a correlation-structure change that
  leaves every marginal alone. It pays for that with a permutation null per
  check and a subsample cap, and its threshold is data-dependent, which makes
  "the alarm fired" harder to standardise across streams.

Where the winner loses, stated rather than hidden:

- PSI is per-feature. A joint shift with untouched marginals is invisible to
  it; MMD exists in the battery for exactly that case, and `scan_features`
  always reports all three readings.
- PSI with open tail bins and a half-count floor underweights a pure tail
  excursion relative to KS on small windows.
- The grid's smallest injected shifts did not cross the threshold: the detector
  **alarmed on 4 of** the **10 harmless streams**, the four with the larger
  magnitudes. A tuned threshold could catch the smaller ones, at the direct
  cost of E4's precision, which is already a **precision of 20.0%** at a
  **prevalence of 10%**.

## Consequences

The choice changes nothing about the repository's finding. The E1 grid shows a
**correlation of -0.001** between the default detector's score and the realized
drop, and swapping PSI for KS or MMD cannot change the sign of that result,
because the harmful injection moves no covariate at all: the detectors differ
only in how they see the harmless one.
