"""The checker itself is code, so it gets the same treatment as the code."""

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import check_numbers  # noqa: E402
import metrics_spec  # noqa: E402


def test_a_floor_rounded_metric_rounds_down_never_to_nearest():
    metrics_spec.METRICS["_t"] = {"fmt": "{:.2f}", "round": "floor", "anchors": []}
    try:
        assert metrics_spec.render("_t", 9.9377) == "9.93"
        assert metrics_spec.render("_t", 9.9399) == "9.93"
    finally:
        del metrics_spec.METRICS["_t"]


def test_a_nearest_rounded_metric_rounds_to_nearest():
    metrics_spec.METRICS["_t"] = {"fmt": "{:.2f}", "round": "nearest", "anchors": []}
    try:
        assert metrics_spec.render("_t", 9.9377) == "9.94"
    finally:
        del metrics_spec.METRICS["_t"]


def test_integer_metrics_render_with_thousands_separators_when_declared():
    metrics_spec.METRICS["_t"] = {"fmt": "{:,d}", "round": "nearest", "anchors": []}
    try:
        assert metrics_spec.render("_t", 16261) == "16,261"
    finally:
        del metrics_spec.METRICS["_t"]


def test_no_anchor_template_exceeds_four_words():
    for name, spec in metrics_spec.METRICS.items():
        for a in spec["anchors"]:
            words = [w for w in a.replace("{}", "X").split() if w]
            assert len(words) <= 4, f"{name}: {a!r} would straddle a wrapped line"


def test_no_two_metrics_share_an_anchor_even_by_containment():
    pairs = [(m, a) for m, s in metrics_spec.METRICS.items() for a in s["anchors"]]
    for mi, ai in pairs:
        for mj, aj in pairs:
            assert not (mi != mj and ai in aj), f"{mi}:{ai!r} contained in {mj}:{aj!r}"


def test_the_reverse_pass_skips_sha_fragments_paths_and_times():
    text = "sha 4f9a12 and path a/2/b and 10:30 time but 42 counts and 3.5 too"
    prose = check_numbers.strip_uncheckable(text)
    found = [m.group(1) for m in check_numbers.BARE_NUMBER.finditer(prose)]
    assert found == ["42", "3.5"]


def test_the_stripper_removes_fences_code_spans_and_html_attributes():
    text = "before\n```\n999\n```\nmid `888` <img width=\"777\"> after v1.2.3 2026-01-07"
    out = check_numbers.strip_uncheckable(text)
    for gone in ("999", "888", "777", "1.2.3", "2026-01-07"):
        assert gone not in out
    assert "before" in out and "after" in out


def test_anchor_regex_matches_the_slot_with_commas_and_sign():
    rx = check_numbers.anchor_regex("correlation of {}")
    assert rx.search("a correlation of -0.001 here").group(1) == "-0.001"
    rx2 = check_numbers.anchor_regex("{} predictions before")
    assert rx2.search("16,261 predictions before day x").group(1) == "16,261"


def _mini_repo(tmp_path, readme: str, rendered: dict, anchors: dict):
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text(readme)
    payload = {
        "metrics": {k: 0 for k in rendered},
        "rendered": rendered,
        "anchors": anchors,
        "checked_documents": ["README.md"],
    }
    (tmp_path / "docs" / "metrics.json").write_text(json.dumps(payload))
    return tmp_path


def _run_checker(monkeypatch, root: Path) -> int:
    monkeypatch.setattr(check_numbers, "ROOT", root)
    monkeypatch.setattr(check_numbers, "METRICS_JSON", root / "docs" / "metrics.json")
    return check_numbers.main()


EXEMPT_LINE = ("alpha 0.05, power 0.80, psi 0.2, floor 95, horizon 100, "
               "day 7, day 18, exits 1 and 3.\n")


def test_the_checker_passes_a_document_whose_figures_match(tmp_path, monkeypatch, capsys):
    root = _mini_repo(
        tmp_path,
        "We saw 42 tests pass.\n" + EXEMPT_LINE,
        {"tests_total": "42"},
        {"tests_total": ["{} tests"]},
    )
    assert _run_checker(monkeypatch, root) == 0


def test_the_checker_fails_a_stale_anchored_figure(tmp_path, monkeypatch, capsys):
    root = _mini_repo(
        tmp_path,
        "We saw 41 tests pass.\n" + EXEMPT_LINE,
        {"tests_total": "42"},
        {"tests_total": ["{} tests"]},
    )
    assert _run_checker(monkeypatch, root) == 1
    assert "carries '41'" in capsys.readouterr().out


def test_the_checker_fails_an_unguarded_number_in_prose(tmp_path, monkeypatch, capsys):
    root = _mini_repo(
        tmp_path,
        "We saw 42 tests pass and 9 dragons.\n" + EXEMPT_LINE,
        {"tests_total": "42"},
        {"tests_total": ["{} tests"]},
    )
    assert _run_checker(monkeypatch, root) == 1
    assert "matches no metric" in capsys.readouterr().out


def test_the_checker_sweeps_inside_fenced_blocks_for_anchors(tmp_path, monkeypatch, capsys):
    root = _mini_repo(
        tmp_path,
        "We saw 42 tests.\n```\n41 tests\n```\n" + EXEMPT_LINE,
        {"tests_total": "42"},
        {"tests_total": ["{} tests"]},
    )
    assert _run_checker(monkeypatch, root) == 1  # the stale copy hides in the fence


def test_the_checker_fails_closed_without_metrics_json(tmp_path, monkeypatch, capsys):
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("hello")
    assert _run_checker(monkeypatch, tmp_path) == 1


def test_the_checker_fails_a_missing_checked_document(tmp_path, monkeypatch, capsys):
    root = _mini_repo(tmp_path, EXEMPT_LINE, {"tests_total": "42"},
                      {"tests_total": ["{} tests"]})
    (root / "README.md").unlink()
    assert _run_checker(monkeypatch, root) == 1
    assert "missing" in capsys.readouterr().out


def test_an_unused_exemption_fails_the_build(tmp_path, monkeypatch, capsys):
    root = _mini_repo(
        tmp_path,
        "We saw 42 tests. alpha 0.05, power 0.80, psi 0.2, "
        "floor 95, day 7, day 18, exits 1 and 3.\n",
        {"tests_total": "42"},
        {"tests_total": ["{} tests"]},
    )
    assert _run_checker(monkeypatch, root) == 1  # 100 never appears
    assert "unused exemptions" in capsys.readouterr().out


def test_an_exemption_equal_to_a_rendered_value_fails(tmp_path, monkeypatch, capsys):
    root = _mini_repo(
        tmp_path,
        "We saw 95 tests pass.\n" + EXEMPT_LINE,
        {"tests_total": "95"},
        {"tests_total": ["{} tests"]},
    )
    assert _run_checker(monkeypatch, root) == 1
    assert "hide drift" in capsys.readouterr().out


def test_containment_between_two_metrics_fails_the_spec(tmp_path, monkeypatch, capsys):
    root = _mini_repo(
        tmp_path,
        "42 tests and 42 tests passed today.\n" + EXEMPT_LINE,
        {"a": "42", "b": "42"},
        {"a": ["{} tests"], "b": ["{} tests passed"]},
    )
    assert _run_checker(monkeypatch, root) == 1
    assert "containment" in capsys.readouterr().out


def test_the_duration_sweep_flags_milliseconds_in_prose(tmp_path):
    import check_durations
    assert check_durations.DURATION.search("took 35 ms on this box")
    assert check_durations.DURATION.search("about 2 seconds of work")
    assert not check_durations.DURATION.search("blind for 20.5 days")
    assert not check_durations.DURATION.search("a secondary concern")
