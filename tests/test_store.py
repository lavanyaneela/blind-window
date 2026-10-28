"""The SQL log: properties of every committed query, and the bug that was real."""

import numpy as np
import pytest

from blind_window.store.log_store import (
    QUERY_NAMES,
    LogStore,
    StoreError,
    declared_columns,
    query_path,
    read_query,
)


@pytest.fixture(scope="module")
def store(tmp_path_factory, harm_stream):
    db = tmp_path_factory.mktemp("db") / "log.duckdb"
    st = LogStore(db)
    st.load_stream(harm_stream)
    yield st
    st.close()


def test_loading_a_stream_fills_both_logs_completely(store, harm_stream):
    n_pred = store.conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    n_lab = store.conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
    assert n_pred == len(harm_stream) == n_lab


def test_meta_round_trips_the_ground_truth(store, harm_stream):
    assert store.meta_value("realized_drop_points") == harm_stream.meta["realized_drop_points"]


def test_a_missing_meta_key_names_itself_and_the_database(store):
    with pytest.raises(StoreError, match="nope"):
        store.meta_value("nope")


def test_a_stream_with_the_wrong_feature_width_is_rejected(tmp_path, clean_stream):
    narrow = clean_stream
    st = LogStore(tmp_path / "w.duckdb")
    import dataclasses
    bad = dataclasses.replace(narrow, features=narrow.features[:, :4])
    with pytest.raises(StoreError, match="feature columns"):
        st.load_stream(bad)
    st.close()


def test_every_query_has_both_dialect_files_with_identical_declarations():
    for name in QUERY_NAMES:
        assert declared_columns("duckdb", name) == declared_columns("postgres", name)


def test_an_unknown_query_name_is_rejected():
    with pytest.raises(StoreError, match="unknown query"):
        query_path("duckdb", "drop_tables")


def test_a_missing_dialect_file_is_reported_with_its_path(tmp_path, monkeypatch):
    import blind_window.store.log_store as mod
    monkeypatch.setattr(mod, "SQL_ROOT", tmp_path)
    with pytest.raises(StoreError, match="missing"):
        query_path("duckdb", "blind_exposure")


def test_a_query_without_a_columns_header_is_rejected(tmp_path, monkeypatch):
    import blind_window.store.log_store as mod
    (tmp_path / "duckdb").mkdir()
    (tmp_path / "duckdb" / "blind_exposure.sql").write_text("SELECT 1 AS x")
    monkeypatch.setattr(mod, "SQL_ROOT", tmp_path)
    with pytest.raises(StoreError, match="columns"):
        declared_columns("duckdb", "blind_exposure")


def test_live_columns_are_checked_against_the_declaration(store, monkeypatch):
    import blind_window.store.log_store as mod
    real = mod.read_query

    def tampered(dialect, name):
        return real(dialect, name).replace("AS labeled_share", "AS share")

    monkeypatch.setattr(mod, "read_query", tampered)
    with pytest.raises(StoreError, match="declares"):
        store.run("blind_exposure", {"onset": 10.0, "asof": 25.0})


def test_labeled_counts_by_day_is_nondecreasing(store):
    _, rows = store.run("labeled_counts_by_day", {"onset": 10.0, "asof": 29.0})
    counts = [r[1] for r in rows]
    assert counts == sorted(counts)


def test_blind_exposure_share_stays_inside_the_unit_interval(store):
    _, rows = store.run("blind_exposure", {"onset": 10.0, "asof": 29.0})
    assert all(0.0 <= r[3] <= 1.0 for r in rows)
    served = [r[1] for r in rows]
    assert served == sorted(served)


def test_latency_deciles_partition_the_arrived_labels(store):
    _, rows = store.run("label_latency_deciles", {"asof": 29.0})
    assert [r[0] for r in rows] == list(range(1, 11))
    n_arrived = store.conn.execute(
        "SELECT COUNT(*) FROM predictions p JOIN labels l USING (request_id) "
        "WHERE l.label_day <= 29.0"
    ).fetchone()[0]
    assert sum(r[1] for r in rows) == n_arrived
    medians = [r[3] for r in rows]
    assert medians == sorted(medians)


def test_version_windows_reports_the_single_serving_version(store, harm_stream):
    _, rows = store.run("version_windows", {"asof": 29.0})
    assert len(rows) == 1 and rows[0][0] == "v1"
    assert rows[0][3] == len(harm_stream)
    assert 0.0 < rows[0][5] < 1.0


def test_maturity_curve_is_a_nondecreasing_share_capped_at_one(store):
    _, rows = store.run("maturity_curve", {"cohort_start": 0.0, "cohort_end": 5.0, "asof": 29.0})
    shares = [r[2] for r in rows]
    assert shares == sorted(shares)
    assert shares[-1] <= 1.0


def test_windowed_accuracy_asof_leaves_unlabeled_days_null(store):
    _, rows = store.run("windowed_accuracy_asof", {"asof": 10.5})
    by_day = {r[0]: r for r in rows}
    fresh = by_day[10]
    assert fresh[1] <= 5  # almost nothing labeled half a day in
    if fresh[1] == 0:
        assert fresh[2] is None


def test_the_asof_accuracy_bug_the_fix_commit_describes_is_really_gone(store):
    """War story: the original query put the label match inside
    CASE WHEN p.predicted = l.y_true, so every unlabeled row fell to ELSE 0.0
    and a healthy fresh cohort reported accuracy near zero. The fixed query
    must agree with a labeled-only recomputation."""
    _, rows = store.run("windowed_accuracy_asof", {"asof": 20.0})
    arrays = store.arrays()
    for day, n_labeled, acc in rows:
        if n_labeled == 0:
            continue
        m = (
            (arrays["ts_day"] >= day)
            & (arrays["ts_day"] < day + 1)
            & (arrays["label_day"] <= 20.0)
        )
        assert acc == pytest.approx(float(np.mean(arrays["correct"][m])))


def test_the_reconstructed_broken_query_fails_the_previous_assertion(store):
    """The regression test above would pass against code that never had the
    bug; this one reconstructs the bug and asserts the detection actually
    detects it (a lesson from project one of this portfolio: a regression test
    needs a companion that proves it can fail)."""
    broken_sql = read_query("duckdb", "windowed_accuracy_asof").replace(
        "CASE WHEN l.request_id IS NULL THEN NULL\n             WHEN",
        "CASE WHEN",
    )
    assert "IS NULL THEN NULL" not in broken_sql
    cur = store.conn.execute(broken_sql, {"asof": 20.0})
    rows = cur.fetchall()
    arrays = store.arrays()
    mismatches = 0
    for day, n_labeled, acc in rows:
        if not n_labeled:
            continue
        m = (
            (arrays["ts_day"] >= day)
            & (arrays["ts_day"] < day + 1)
            & (arrays["label_day"] <= 20.0)
        )
        if acc != pytest.approx(float(np.mean(arrays["correct"][m]))):
            mismatches += 1
    assert mismatches > 0, "the reconstructed bug produced correct output; the test proves nothing"


def test_feature_matrix_returns_the_requested_slice(store, harm_stream):
    mat = store.feature_matrix(0.0, 5.0)
    expected = int(np.count_nonzero(harm_stream.ts_day < 5.0))
    assert mat.shape == (expected, 6)
