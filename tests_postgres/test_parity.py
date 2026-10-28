"""Dialect parity, executed: every query, row for row, DuckDB against Postgres.

This file lives outside the default testpaths on purpose: it needs a real
PostgreSQL server (POSTGRES_DSN), so collecting it locally would make the
published test count depend on what a machine has installed. CI runs it as a
required job against a postgres:16 service container; `make verify` stays
offline on DuckDB. The parity contract: identical column names (declared in
each file's header) and identical rows on the same fixture, within float
tolerance.
"""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

import psycopg
import pytest

from blind_window.scenario import Scenario
from blind_window.simulate.stream import generate
from blind_window.store.log_store import (
    N_FEATURE_COLUMNS,
    QUERY_NAMES,
    LogStore,
    declared_columns,
    read_query,
)

DSN = os.environ.get("POSTGRES_DSN")
if not DSN:  # pragma: no cover - CI sets the DSN; local runs never collect this
    pytest.skip("POSTGRES_DSN not set; parity runs in CI", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
PARAMS = {
    "labeled_counts_by_day": {"onset": 15.0, "asof": 34.5},
    "windowed_accuracy_asof": {"asof": 35.0},
    "label_latency_deciles": {"asof": 35.0},
    "blind_exposure": {"onset": 15.0, "asof": 34.5},
    "version_windows": {"asof": 35.0},
    "maturity_curve": {"cohort_start": 0.0, "cohort_end": 10.0, "asof": 8.5},
}


@pytest.fixture(scope="module")
def stores():
    stream = generate(Scenario.load(ROOT / "fixtures/scenarios/warstory.json"))
    with tempfile.TemporaryDirectory() as td:
        duck = LogStore(Path(td) / "parity.duckdb")
        duck.load_stream(stream)
        with psycopg.connect(DSN) as pg:
            with pg.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS predictions, labels")
                feats = ", ".join(
                    f"f{i} double precision NOT NULL" for i in range(N_FEATURE_COLUMNS)
                )
                cur.execute(
                    f"CREATE TABLE predictions (request_id bigint PRIMARY KEY, "
                    f"ts_day double precision NOT NULL, score double precision NOT NULL, "
                    f"predicted smallint NOT NULL, model_version varchar NOT NULL, {feats})"
                )
                cur.execute(
                    "CREATE TABLE labels (request_id bigint PRIMARY KEY, "
                    "label_day double precision NOT NULL, y_true smallint NOT NULL)"
                )
                with cur.copy("COPY predictions FROM STDIN") as copy:
                    for i in range(len(stream)):
                        copy.write_row(
                            (
                                int(stream.request_id[i]),
                                float(stream.ts_day[i]),
                                float(stream.score[i]),
                                int(stream.predicted[i]),
                                "v1",
                                *[float(v) for v in stream.features[i]],
                            )
                        )
                with cur.copy("COPY labels FROM STDIN") as copy:
                    for i in range(len(stream)):
                        copy.write_row(
                            (
                                int(stream.request_id[i]),
                                float(stream.label_day[i]),
                                int(stream.y_true[i]),
                            )
                        )
            pg.commit()
            yield duck, pg
        duck.close()


def _close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    return a == b


@pytest.mark.parametrize("name", QUERY_NAMES)
def test_the_two_dialects_return_identical_rows(stores, name):
    duck, pg = stores
    cols_duck, rows_duck = duck.run(name, PARAMS[name])
    with pg.cursor() as cur:
        cur.execute(read_query("postgres", name), PARAMS[name])
        cols_pg = tuple(d.name for d in cur.description)
        rows_pg = cur.fetchall()
    assert cols_pg == declared_columns("postgres", name) == cols_duck
    assert len(rows_pg) == len(rows_duck), f"{name}: row counts differ"
    for rd, rp in zip(rows_duck, rows_pg, strict=True):
        assert all(_close(a, b) for a, b in zip(rd, rp, strict=True)), (
            f"{name}: {rd} != {rp}"
        )
