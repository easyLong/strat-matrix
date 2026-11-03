"""Acceptance checks for the regression tool, including its negative paths."""
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import sys

import pymysql
import pytest

from testing import run
from testing.datasets import ROOT, TYPES, STAGES, build, digest, load
from testing.evaluate import evaluate, offline_boundary
from testing.report import baseline_snapshot, compare, validate_baseline_for_recording, write_reports


@pytest.fixture(scope="module")
def current():
    return evaluate(load("small"))


@pytest.mark.parametrize("name,accounts,topics", [("small", 5, 60), ("scale", 100, 600)])
def test_committed_datasets_are_reproducible_and_explicitly_synthetic(name, accounts, topics):
    value = load(name)
    assert digest(build(name)) == digest(value)
    assert len(value["accounts"]) == accounts and len(value["topics"]) == topics
    assert len(value["positions"]) == 3 * accounts
    assert {a["profile"]["lifecycle_stage"] for a in value["accounts"]} == set(STAGES)
    assert {t["source_payload"]["content_type"] for t in value["topics"]} == set(TYPES)
    assert value["data_origin"] == "synthetic_only"
    assert all(a["account_id"].startswith("SYN-") for a in value["accounts"])


def test_actual_executors_match_pinned_results_and_exercise_quality_gates(current):
    baseline = json.loads((ROOT / "testing/baselines/small-v19.json").read_text(encoding="utf-8"))
    assert compare(baseline, current)["status"] == "passed"
    assert current["real_model_calls"] == current["production_writes"] == 0
    assert set(current["engines"]) == {"v19"}
    assert current["engines"]["v19"]["quality"]["worker_turn"]["model_calls"] == 0
    assert all(v["metrics"]["matched_positions"] == 15 for v in current["engines"].values())
    dataset = load("small")
    quality = current["engines"]["v19"]["quality"]
    for scenario, reason in [("wrong_city", "region_not_allowed"), ("unmapped", "unmapped_primary_topic"),
                             ("history", "observed_history"), ("related_off", "persona_off")]:
        topic = next(t for t in dataset["topics"] if t["scenario"] == scenario)
        causes = [r["reason"] for a in quality["accounts"].values() for r in a["recall"]["rejected"] if r["topic_id"] == topic["topic_id"]]
        assert reason in causes
    for scenario in ("model_drop", "conditional_reject"):
        topic = next(t for t in dataset["topics"] if t["scenario"] == scenario)
        decisions = [p for a in quality["accounts"].values() for p in a["precision"] if p["topic_id"] == topic["topic_id"]]
        assert decisions and all(not p["accepted"] for p in decisions)


def test_result_selection_changes_require_review_even_when_totals_match(current):
    baseline = baseline_snapshot(current)
    baseline["engines"]["v19"]["positions"][0]["topic_id"] = "OTHER-CHOICE"
    result = compare(baseline, current)
    assert result["status"] == "review"
    assert result["changes"][0]["fields"] == ["topic_id"]


def test_different_data_or_model_spaces_are_not_comparable(current):
    for field in ("dataset_hash", "vector_space", "mode"):
        baseline = baseline_snapshot(current)
        baseline[field] = "different"
        assert compare(baseline, current)["status"] == "incomparable"


def test_retired_algorithms_are_not_accepted_and_report_has_no_dual_engine_ui(tmp_path, current):
    with pytest.raises(ValueError, match='Only V19'):
        evaluate(load('small'), engine_filter=['v2'])
    with pytest.raises(ValueError, match='Only V19'):
        evaluate(load('small'), {'v2': {}})
    result = deepcopy(current)
    result['comparison'] = compare(baseline_snapshot(current), current)
    write_reports(tmp_path, result)
    html = (tmp_path / 'report.html').read_text(encoding='utf-8')
    assert '<th>V2</th>' not in html and 'id="engine"' not in html
    assert set(result['engines']) == {'v19'}


def test_bad_candidate_policy_fails_gates_instead_of_becoming_new_baseline(current):
    candidate = deepcopy(load("small")["policies"]["v19"])
    candidate["quality"]["minimum_precision"] = .99
    result = evaluate(load("small"), {"v19": candidate})
    assert compare(baseline_snapshot(current), result)["status"] == "failed"
    assert result["engines"]["v19"]["metrics"]["failed_positions"] == 15
    with pytest.raises(ValueError):
        validate_baseline_for_recording(result)


def test_network_and_database_are_blocked_without_touching_running_services():
    with offline_boundary():
        with pytest.raises(RuntimeError, match="离线"):
            pymysql.connect(host="127.0.0.1")
        with socket.socket() as client, pytest.raises(RuntimeError, match="离线"):
            client.connect(("127.0.0.1", 6930))


def test_html_is_self_contained_and_escapes_data(tmp_path, current):
    result = deepcopy(current)
    result["accounts"][0]["account_name"] = '<img src=x onerror="alert(1)">'
    result["comparison"] = compare(baseline_snapshot(current), current)
    write_reports(tmp_path, result)
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "&lt;img" in html and "<img src=x" not in html
    assert '<script src=' not in html and '<link ' not in html
    assert json.loads((tmp_path / "algorithm.json").read_text(encoding="utf-8"))["real_model_calls"] == 0


def test_failed_and_timed_out_commands_are_not_green(tmp_path):
    failed = run.command_step("failed", [sys.executable, "-c", "raise SystemExit(7)"], ROOT, tmp_path, os.environ, 10)
    assert failed["status"] == "failed" and failed["exit_code"] == 7
    timed = run.command_step("timed", [sys.executable, "-c", "import time;time.sleep(5)"], ROOT, tmp_path, os.environ, .1)
    assert timed["status"] == "timeout" and timed["exit_code"] == 124


def test_missing_tool_fails_and_writes_a_summary(monkeypatch, tmp_path):
    def unavailable(*_args):
        raise ValueError("缺少工具")
    monkeypatch.setattr(run, "executable", unavailable)
    assert run.main(["--suite", "java", "--output", str(tmp_path)]) == 1
    assert json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))["steps"][0]["status"] == "unavailable"


def test_normal_run_keeps_baseline_and_previous_reports_immutable(tmp_path):
    path = ROOT / "testing/baselines/small-v19.json"
    before = path.read_bytes()
    assert run.main(["--suite", "algorithm", "--output", str(tmp_path)]) == 0
    assert path.read_bytes() == before
    with pytest.raises(SystemExit):
        run.main(["--suite", "algorithm", "--output", str(tmp_path)])


def test_tampered_dataset_is_rejected_before_any_algorithm_runs(tmp_path, monkeypatch):
    from testing import datasets
    original = load("small")
    manifest = json.loads((datasets.DATA / "manifest.json").read_text(encoding="utf-8"))
    original["accounts"][0]["account_name"] = "unexpected edit"
    (tmp_path / "small.json").write_text(json.dumps(original), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(datasets, "DATA", tmp_path)
    with pytest.raises(ValueError, match="指纹"):
        datasets.load("small")
