"""Assembles and writes the machine-readable evaluation report.

The JSON shape is deliberately flat and per-subsystem -- there is no
single combined "AI accuracy" number anywhere in it. See
``evaluation.metrics``'s own docstring for why.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from evaluation.metrics import overall_counts
from evaluation.runners.base import EvalResult, summarize

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


@dataclass(frozen=True)
class SubsystemRun:
    name: str
    results: list[EvalResult]


def build_report(subsystem_runs: list[SubsystemRun], offline: bool = True) -> dict:
    subsystems = {run.name: summarize(run.name, run.results).to_dict() for run in subsystem_runs}
    overall = overall_counts(subsystems)
    overall["pass_rate"] = round(overall["passed"] / overall["total"], 4) if overall["total"] else 0.0

    return {
        "run_id": uuid.uuid4().hex[:12],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "offline": offline,
        "overall": overall,
        "subsystems": subsystems,
        "not_a_clinical_benchmark": (
            "This report measures engineering/behavioral correctness and safety "
            "compliance against synthetic, version-controlled fixtures. It proves "
            "nothing about real-world dermatological or medical accuracy. See "
            "docs/evaluation.md."
        ),
    }


def write_report(report: dict, path: Path | None = None) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    target = path or (REPORTS_DIR / f"eval-{report['run_id']}.json")
    # Verify the report is actually JSON-safe before writing anything --
    # a failure here means a runner leaked a non-primitive value into a
    # result, which must be fixed in that runner, not swallowed here.
    text = json.dumps(report, indent=2)
    target.write_text(text)

    latest = REPORTS_DIR / "latest.json"
    latest.write_text(text)
    return target


def print_summary(report: dict) -> None:
    print(f"Evaluation run {report['run_id']} ({report['timestamp']})")
    print(f"Offline: {report['offline']}")
    print()
    for name, summary in report["subsystems"].items():
        print(
            f"  {name:12s} total={summary['total']:3d}  passed={summary['passed']:3d}  "
            f"failed={summary['failed']:3d}  pass_rate={summary['pass_rate']:.2%}"
        )
        for failure in summary["failures"]:
            print(f"      FAIL {failure['case_id']}: {failure['message']}")
    print()
    overall = report["overall"]
    print(f"  {'OVERALL':12s} total={overall['total']:3d}  passed={overall['passed']:3d}  failed={overall['failed']:3d}")
