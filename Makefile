# blind-window build targets.
#
# make itself returns 2 for any failed recipe, which would collide with this
# project's exit code 2 (refused: inside the blind window). Targets that run
# the CLI therefore print the tool's exit code and return 0; branch on the
# console script, not on make.

PY ?= python3

.PHONY: install lint test receipts verify demo report set-handle experiments

install:
	$(PY) -m pip install -e ".[dev]"

lint:
	$(PY) -m ruff check src tests tools experiments

test:
	$(PY) -m pytest --junitxml=.pytest-junit.xml --cov=blind_window --cov-report=json --cov-report=term-missing:skip-covered

experiments:
	$(PY) experiments/run_all.py

receipts:
	$(PY) tools/collect_metrics.py
	$(PY) tools/check_numbers.py
	$(PY) tools/check_durations.py

verify: lint test experiments receipts

demo:
	@$(PY) -m blind_window.cli simulate --scenario fixtures/scenarios/default.json --db runs/demo.duckdb --force
	@$(PY) -m blind_window.cli check --db runs/demo.duckdb --asof-day 33 --drop 0.05; echo "blind-window exit code: $$?"

report:
	@$(PY) -m blind_window.cli report --db runs/demo.duckdb --asof-day 33 --drop 0.05 || true

# Replace the placeholder GitHub handle everywhere it appears, then insert the
# CI badge (a badge pointing at a repo that does not exist renders "unknown").
set-handle:
	@test -n "$(HANDLE)" || (echo "usage: make set-handle HANDLE=your-github-handle" && exit 1)
	$(PY) tools/set_handle.py "$(HANDLE)"
