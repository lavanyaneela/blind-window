# Changelog

All notable changes to this project are documented here. The format follows
Keep a Changelog; versions are annotated git tags.

## [1.0.0]

### Fixed
- Findings from the forensics audit, each in its own commit.

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
  healthy fresh cohorts; see the fix commit and the war story in the README.
