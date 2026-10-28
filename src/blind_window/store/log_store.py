"""Append-only prediction and label log over SQL.

Monitoring state is two immutable event streams: a prediction happened, a
label arrived. Everything the tool reports is a time-windowed query over that
log, so the queries live in committed .sql files (sql/duckdb/ and
sql/postgres/), not in Python strings: they are the interesting part, they are
reviewed as SQL, and the two dialects are kept in parity by test.

DuckDB is the default engine and the only one make verify needs. The Postgres
dialect executes in CI against a real postgres:16 service container as a
required job; the parity contract is row-for-row equality on the same fixture.
"""

from __future__ import annotations

import csv
import json
import re
import tempfile
from pathlib import Path

import duckdb
import numpy as np

from blind_window.simulate.stream import Stream

SQL_ROOT = Path(__file__).resolve().parents[3] / "sql"
QUERY_NAMES = (
    "labeled_counts_by_day",
    "windowed_accuracy_asof",
    "label_latency_deciles",
    "blind_exposure",
    "version_windows",
    "maturity_curve",
)
N_FEATURE_COLUMNS = 6


class StoreError(ValueError):
    """Raised when the log or a query cannot be used as asked."""


def query_path(dialect: str, name: str) -> Path:
    if name not in QUERY_NAMES:
        raise StoreError(f"unknown query {name!r}; known: {QUERY_NAMES}")
    p = SQL_ROOT / dialect / f"{name}.sql"
    if not p.exists():
        raise StoreError(f"missing {dialect} dialect for query {name!r}: {p}")
    return p


def declared_columns(dialect: str, name: str) -> tuple[str, ...]:
    """Every query file declares its output columns in a header comment. The
    declaration is the structural parity contract between dialects, and the
    DuckDB result is tested against it, so the comment cannot rot."""
    text = query_path(dialect, name).read_text()
    m = re.search(r"^--\s*columns:\s*(.+)$", text, flags=re.MULTILINE)
    if not m:
        raise StoreError(f"query {name!r} ({dialect}) has no '-- columns:' header")
    return tuple(c.strip() for c in m.group(1).split(","))


def read_query(dialect: str, name: str) -> str:
    return query_path(dialect, name).read_text()


class LogStore:
    """One DuckDB database holding the two logs and the scenario ground truth."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.conn = duckdb.connect(str(self.db_path))

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        feats = ", ".join(f"f{i} DOUBLE NOT NULL" for i in range(N_FEATURE_COLUMNS))
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS predictions ("
            f"request_id BIGINT PRIMARY KEY, ts_day DOUBLE NOT NULL, score DOUBLE NOT NULL, "
            f"predicted SMALLINT NOT NULL, model_version VARCHAR NOT NULL, {feats})"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS labels ("
            "request_id BIGINT PRIMARY KEY, label_day DOUBLE NOT NULL, y_true SMALLINT NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL)"
        )

    def load_stream(self, stream: Stream, model_version: str = "v1") -> int:
        """Bulk load via CSV COPY: dependency-free and fast enough for 10^5 rows."""
        if stream.features.shape[1] != N_FEATURE_COLUMNS:
            raise StoreError(
                f"store schema holds {N_FEATURE_COLUMNS} feature columns, "
                f"stream has {stream.features.shape[1]}"
            )
        self.init_schema()
        with tempfile.TemporaryDirectory() as td:
            pred_csv = Path(td) / "predictions.csv"
            lab_csv = Path(td) / "labels.csv"
            with pred_csv.open("w", newline="") as fh:
                w = csv.writer(fh)
                for i in range(len(stream)):
                    w.writerow(
                        [
                            int(stream.request_id[i]),
                            float(stream.ts_day[i]),
                            float(stream.score[i]),
                            int(stream.predicted[i]),
                            model_version,
                            *[float(v) for v in stream.features[i]],
                        ]
                    )
            with lab_csv.open("w", newline="") as fh:
                w = csv.writer(fh)
                for i in range(len(stream)):
                    w.writerow(
                        [
                            int(stream.request_id[i]),
                            float(stream.label_day[i]),
                            int(stream.y_true[i]),
                        ]
                    )
            self.conn.execute(f"COPY predictions FROM '{pred_csv}' (HEADER FALSE)")
            self.conn.execute(f"COPY labels FROM '{lab_csv}' (HEADER FALSE)")
        meta = dict(stream.meta)
        meta["scenario_json"] = json.dumps(
            {
                "name": stream.scenario.name,
                "seed": stream.scenario.seed,
                "horizon_days": stream.scenario.horizon_days,
                "rate_per_day": stream.scenario.rate_per_day,
            }
        )
        for k, v in meta.items():
            self.conn.execute(
                "INSERT OR REPLACE INTO meta VALUES (?, ?)", [k, json.dumps(v)]
            )
        return len(stream)

    def meta_value(self, key: str):
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", [key]).fetchone()
        if row is None:
            raise StoreError(f"meta key {key!r} not found in {self.db_path}")
        return json.loads(row[0])

    def run(self, name: str, params: dict) -> tuple[tuple[str, ...], list[tuple]]:
        """Execute a named DuckDB-dialect query; returns (columns, rows) and
        asserts the live columns match the file's declaration."""
        sql = read_query("duckdb", name)
        cur = self.conn.execute(sql, params)
        cols = tuple(d[0] for d in cur.description)
        declared = declared_columns("duckdb", name)
        if cols != declared:
            raise StoreError(
                f"query {name!r} returned columns {cols}, file declares {declared}"
            )
        return cols, cur.fetchall()

    def arrays(self) -> dict[str, np.ndarray]:
        """The joined log as numpy arrays for the python-side computations."""
        rows = self.conn.execute(
            "SELECT p.ts_day, l.label_day, CAST(p.predicted = l.y_true AS SMALLINT) AS correct, "
            "p.score FROM predictions p JOIN labels l USING (request_id) ORDER BY p.request_id"
        ).fetchnumpy()
        return {
            "ts_day": np.asarray(rows["ts_day"], dtype=float),
            "label_day": np.asarray(rows["label_day"], dtype=float),
            "correct": np.asarray(rows["correct"], dtype=np.int8),
            "score": np.asarray(rows["score"], dtype=float),
        }

    def feature_matrix(self, start_day: float, end_day: float) -> np.ndarray:
        cols = ", ".join(f"f{i}" for i in range(N_FEATURE_COLUMNS))
        rows = self.conn.execute(
            f"SELECT {cols} FROM predictions WHERE ts_day >= ? AND ts_day < ? "
            f"ORDER BY request_id",
            [start_day, end_day],
        ).fetchnumpy()
        return np.column_stack([rows[f"f{i}"] for i in range(N_FEATURE_COLUMNS)])
