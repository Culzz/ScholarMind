"""The CI gate must refuse to certify a run that measured nothing.

The old gate exited 0 when it found no results, which reported safety it did not
have; the lexical stub also scored a perfect recall by echoing the gold ids.
"""

from __future__ import annotations

import json
from pathlib import Path

from research.evaluation import gate


def _write(tmp_path: Path, payload: dict) -> Path:
    run_dir = tmp_path / "A" / "20260101T000000Z"
    run_dir.mkdir(parents=True)
    path = run_dir / "results.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _payload(**overrides):
    payload = {
        "dataset_version": "bench-v1",
        "split": "dev",
        "config": {"measurement_valid": True},
        "model_id": "test-model",
        "metrics": {
            "count": 12,
            "false_eligible_rate": 0.0,
            "citation_precision": 0.95,
            "answer_correctness": 0.8,
            "recall_at_10": 0.85,
            "by_question_type": {},
        },
    }
    payload.update(overrides)
    return payload


def test_no_results_is_a_failure(tmp_path: Path) -> None:
    exit_code = gate.main(["--results-root", str(tmp_path)])

    assert exit_code == 2


def test_empty_results_file_is_a_failure(tmp_path: Path) -> None:
    run_dir = tmp_path / "A" / "stamp"
    run_dir.mkdir(parents=True)
    (run_dir / "results.json").write_text("", encoding="utf-8")

    assert gate.main(["--results-root", str(tmp_path)]) == 2


def test_a_stub_run_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, _payload(system_id="lexical-stub"))

    assert gate.main(["--results", str(path)]) == 2


def test_an_explicitly_invalid_run_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, _payload(config={"measurement_valid": False}))

    assert gate.main(["--results", str(path)]) == 2


def test_a_valid_run_that_passes_returns_zero(tmp_path: Path) -> None:
    path = _write(tmp_path, _payload())

    assert gate.main(["--results", str(path)]) == 0


def test_a_missing_metric_fails_the_gate(tmp_path: Path) -> None:
    payload = _payload()
    del payload["metrics"]["recall_at_10"]
    path = _write(tmp_path, payload)

    assert gate.main(["--results", str(path)]) == 1


def test_a_regression_fails_the_gate(tmp_path: Path) -> None:
    payload = _payload()
    payload["metrics"]["citation_precision"] = 0.1
    path = _write(tmp_path, payload)

    assert gate.main(["--results", str(path)]) == 1
