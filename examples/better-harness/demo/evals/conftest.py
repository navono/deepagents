"""Conftest for task-assistant demo evals."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

COUNTS = {"passed": 0, "failed": 0, "skipped": 0}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--model", action="store", default="demo-model")
    parser.addoption("--evals-report-file", action="store", default="")


@pytest.fixture
def model(pytestconfig: pytest.Config) -> str:
    return str(pytestconfig.getoption("--model"))


def pytest_configure(config: pytest.Config) -> None:
    del config
    for key in COUNTS:
        COUNTS[key] = 0


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when != "call":
        return
    if report.passed:
        COUNTS["passed"] += 1
    elif report.failed:
        COUNTS["failed"] += 1
    elif report.skipped:
        COUNTS["skipped"] += 1


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del exitstatus
    summary_file = str(session.config.getoption("--evals-report-file"))
    if not summary_file:
        return
    total = COUNTS["passed"] + COUNTS["failed"] + COUNTS["skipped"]
    payload = {
        "created_at": "demo",
        "sdk_version": "demo",
        "model": str(session.config.getoption("--model")),
        "passed": COUNTS["passed"],
        "failed": COUNTS["failed"],
        "skipped": COUNTS["skipped"],
        "total": total,
        "correctness": 0.0 if total == 0 else COUNTS["passed"] / total,
    }
    path = Path(summary_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
