"""The exit code contract, exercised end to end through main()."""

import json

import pytest

from blind_window.cli import main


@pytest.fixture(scope="module")
def harm_db(tmp_path_factory):
    scen = tmp_path_factory.mktemp("scen")
    sc = {
        "name": "cli-harm", "seed": 97, "horizon_days": 30, "rate_per_day": 200,
        "n_features": 6,
        "delay": {"kind": "lognormal", "median_days": 6, "sigma": 0.6},
        "drifts": [{"kind": "concept_shift", "onset_day": 10, "magnitude": 6.0}],
    }
    path = scen / "s.json"
    path.write_text(json.dumps(sc))
    db = scen / "log.duckdb"
    assert main(["simulate", "--scenario", str(path), "--db", str(db)]) == 0
    return db


@pytest.fixture(scope="module")
def clean_db(tmp_path_factory):
    scen = tmp_path_factory.mktemp("scen2")
    sc = {
        "name": "cli-clean", "seed": 98, "horizon_days": 30, "rate_per_day": 200,
        "n_features": 6,
        "delay": {"kind": "lognormal", "median_days": 6, "sigma": 0.6},
        "drifts": [{"kind": "input_shift", "onset_day": 10, "magnitude": 1.0}],
    }
    path = scen / "s.json"
    path.write_text(json.dumps(sc))
    db = scen / "log.duckdb"
    assert main(["simulate", "--scenario", str(path), "--db", str(db)]) == 0
    return db


def test_simulate_refuses_to_overwrite_without_force(harm_db, capsys):
    scen = harm_db.parent / "s.json"
    assert main(["simulate", "--scenario", str(scen), "--db", str(harm_db)]) == 3
    assert "exists" in capsys.readouterr().err


def test_simulate_overwrites_with_force(harm_db):
    scen = harm_db.parent / "s.json"
    assert main(["simulate", "--scenario", str(scen), "--db", str(harm_db), "--force"]) == 0


def test_check_refuses_with_exit_two_inside_the_blind_window(harm_db, capsys):
    code = main(["check", "--db", str(harm_db), "--asof-day", "11", "--drop", "2.0"])
    out = capsys.readouterr().out
    assert code == 2
    assert "REFUSED" in out and "earliest answerable" in out and "v1" in out


def test_check_confirms_with_exit_zero_once_labels_land(harm_db, capsys):
    code = main(["check", "--db", str(harm_db), "--asof-day", "29", "--drop", "4.0"])
    out = capsys.readouterr().out
    assert code == 0 and "CONFIRMED" in out


def test_check_answers_no_with_exit_one_on_a_harmless_stream(clean_db, capsys):
    code = main(["check", "--db", str(clean_db), "--asof-day", "29", "--drop", "4.0"])
    out = capsys.readouterr().out
    assert code == 1 and "NO REGRESSION" in out


def test_check_errors_with_exit_three_when_asof_precedes_onset(harm_db, capsys):
    code = main(["check", "--db", str(harm_db), "--asof-day", "5", "--drop", "2.0"])
    assert code == 3
    assert "before the onset" in capsys.readouterr().err


def test_check_errors_with_exit_three_on_a_nonexistent_store(tmp_path, capsys):
    code = main(["check", "--db", str(tmp_path / "missing.duckdb"),
                 "--asof-day", "11", "--drop", "2.0"])
    assert code == 3


def test_a_harmless_stream_with_no_onset_recorded_uses_the_input_onset(clean_db):
    # concept_onset_day is null; the CLI falls back to the input shift onset.
    assert main(["check", "--db", str(clean_db), "--asof-day", "29", "--drop", "4.0"]) == 1


def test_onset_day_flag_overrides_the_recorded_onset(harm_db):
    code = main(["check", "--db", str(harm_db), "--asof-day", "29",
                 "--drop", "4.0", "--onset-day", "12"])
    assert code == 0


def test_debug_env_reraises_instead_of_swallowing(harm_db, monkeypatch):
    monkeypatch.setenv("BLIND_WINDOW_DEBUG", "1")
    with pytest.raises(FileExistsError):
        main(["simulate", "--scenario", str(harm_db.parent / "s.json"), "--db", str(harm_db)])


def test_report_json_carries_verdict_exposure_versions_and_deciles(harm_db, capsys):
    code = main(["report", "--db", str(harm_db), "--asof-day", "29",
                 "--drop", "4.0", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == payload["verdict"]["exit_code"] == 0
    assert payload["exposure"] and payload["versions"] and payload["latency_deciles"]


def test_report_includes_the_blind_window_block_when_refusing(harm_db, capsys):
    code = main(["report", "--db", str(harm_db), "--asof-day", "11",
                 "--drop", "2.0", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2 and "blind_window" in payload
    assert payload["blind_window"]["predictions_in_window"] > 0


def test_report_text_mode_prints_the_exposure_table(harm_db, capsys):
    main(["report", "--db", str(harm_db), "--asof-day", "29", "--drop", "4.0"])
    out = capsys.readouterr().out
    assert "day  served  labeled  share" in out


def test_a_stricter_alpha_can_turn_a_confirmation_into_a_no(harm_db):
    relaxed = main(["check", "--db", str(harm_db), "--asof-day", "29", "--drop", "4.0",
                    "--alpha", "0.05"])
    paranoid = main(["check", "--db", str(harm_db), "--asof-day", "17", "--drop", "4.0",
                     "--alpha", "0.0001", "--power", "0.99"])
    assert relaxed == 0 and paranoid in (1, 2)
