# Changelog

All notable changes to this project are documented here. The format follows
Keep a Changelog; versions are annotated git tags.

## [Unreleased]

### Changed
- KS readings now carry the critical statistic as their threshold, so all
  three detectors share one firing semantics; a positive-firing KS test pins
  it.
- The MMD permutation null grew from two hundred draws to a thousand, so its
  0.99 firing quantile has tail mass behind it.
- Published minima floor on integer renders too, and bounds stated as "below"
  round up; the E5 exchange rate therefore corrected downward by one.
- E5 registers every label-confirmed retrain in the MLflow registry with its
  serving start and trigger, and cross-checks the registry's listing. A
  positive-firing KS test pins the firing and the critical-statistic formula.

### Fixed
- Forensics audit pass 1: a fractional as-of leaked labels and predictions
  from the remainder of its own day into both as-of queries (clamped in
  both dialects, pinned by a regression test); the CI count-equality step
  counted zero collected tests under doubled quietness and failed by
  construction; the dead zero-floor guard left the bisection; documents
  stopped overstating what executes where, which cohort was healthy, and what
  the registry records; the junit artifact left tracking; the handle
  placeholder gained real sites and the filler stopped rewriting itself; the
  evidence transcript prints the command that ran.
- Forensics audit pass 2 (the fixes audited): the as-of clamp propagated to
  the maturity cohort and cross-dialect parity now runs at a fractional ask;
  ADR-002 claims only tests that exist; grants and disclosures told apart in
  ADR-004; this changelog stopped under-reporting the pass 1 surface.

## [0.3.0]

### Added
- README, five ADRs and the defense guide, every figure anchored to
  `docs/metrics.json` and enforced by `tools/check_numbers.py`.
- Byte-stable evidence: the exposure curve SVG and the captured day-44 refusal.
- CI: lint, a three-Python matrix with a coverage floor and a
  collected-equals-published count step, a required PostgreSQL parity job on a
  real server, and a receipts job that re-measures every figure, proves the
  checker by breaking one, and diffs the evidence like a fixture.
- The war story became measurable: its scenario is committed and the collector
  re-derives all three figures by reconstructing the broken query.

## [0.2.0]

### Added
- The full test suite, including the reconstructed-bug companion test and the
  import-blocking test that keeps the minimal install working without mlflow.
- Experiments E1 to E5 with committed measurements.
- Receipts tooling: metric spec, collector, checker, duration sweep, prove
  step, handle filler.

## [0.1.0]

### Added
- Seeded stream simulator with independent input and concept injections.
- Power core: minimum detectable drop, the blind window walk, the three-way
  verdict.
- Append-only SQL log on DuckDB with six committed queries in two dialects.
- Input detectors (PSI, KS, permutation MMD), as-of label metrics.
- CLI with the four-code contract; MLflow SQLite registry; retraining policies.

### Fixed
- The as-of accuracy query counted unlabeled predictions as wrong, convicting
  fresh cohorts; see the fix commit and the war story in the README.
