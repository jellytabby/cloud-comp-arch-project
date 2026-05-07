from __future__ import annotations

import glob
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from openevolve.evaluation_result import EvaluationResult


JOBS = [
    "barnes",
    "blackscholes",
    "canneal",
    "freqmine",
    "radix",
    "streamcluster",
    "vips",
]


def _parse_all_measurements(path: Path) -> List[Dict[str, Any]]:
    """
    Parse a single mcperf file (raw TSV or JSON-wrapped stdout).
    Returns a list of dicts sorted by ts_start:
        p95      float  ms
        ts_start int    unix ms
        ts_end   int    unix ms
    """
    raw = path.read_text().strip()

    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 20:
            continue
        try:
            rows.append(
                {
                    "p95": float(parts[12]) / 1000.0,  # us -> ms
                    "ts_start": int(parts[18]),
                    "ts_end": int(parts[19]),
                }
            )
        except (ValueError, IndexError):
            continue

    rows.sort(key=lambda r: r["ts_start"])
    return rows


def _slice_measurements(
    all_measurements: List[Dict[str, Any]],
    pods: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    starts = [p["cstart"] for p in pods if p["job"] in JOBS and p["cstart"]]
    ends = [p["cend"] for p in pods if p["job"] in JOBS and p["cend"]]
    if not starts or not ends:
        return []
    window_start = min(starts) * 1e3
    window_end = max(ends) * 1e3
    window_measurements = []
    for measurement in all_measurements:
        if measurement["ts_start"] >= window_start and measurement["ts_end"] <= window_end:
            window_measurements.append(measurement)
        elif measurement["ts_start"] <= window_start < measurement["ts_end"]:
            window_measurements.append(measurement)
        elif measurement["ts_start"] <= window_end < measurement["ts_end"]:
            window_measurements.append(measurement)
    return window_measurements


def _parse_pods(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text())

    def parse_dt(value: Optional[str]) -> Optional[float]:
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()

    pods = []
    for item in data.get("items", []):
        statuses = item.get("status", {}).get("containerStatuses", [])
        if not statuses:
            continue
        name = statuses[0]["name"][7:]
        node = item.get("spec", {}).get("nodeName", "unknown")[:-5]

        state = statuses[0].get("state", {})
        term = state.get("terminated", {})
        run_s = state.get("running", {})

        cstart = parse_dt(term.get("startedAt") or run_s.get("startedAt"))
        cend = parse_dt(term.get("finishedAt"))

        if name in JOBS:
            pods.append({"job": name, "node": node, "cstart": cstart, "cend": cend})
    return pods


def _compute_makespan(pods: List[Dict[str, Any]]) -> Optional[float]:
    starts = [p["cstart"] for p in pods if p["job"] in JOBS and p["cstart"]]
    ends = [p["cend"] for p in pods if p["job"] in JOBS and p["cend"]]
    return (max(ends) - min(starts)) if (starts and ends) else None


def _compute_slo_violation_ratio(measurements: List[Dict[str, Any]]) -> Optional[float]:
    if not measurements:
        return None
    violations = sum(1 for m in measurements if m["p95"] > 1.0)
    return violations / len(measurements)


def _mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _extract_version(program_text: str) -> Optional[str]:
    match = re.search(r"^\s*VERSION\s*=\s*(\d+)\s*$", program_text, re.MULTILINE)
    return match.group(1) if match else None


def _find_latest_results_dir(results_root: Path) -> Optional[Path]:
    candidates = [p for p in results_root.glob("version*") if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _load_run_files(results_dir: Path) -> List[Path]:
    return [Path(p) for p in sorted(glob.glob(str(results_dir / "run*.json")))]


def _evaluate_results(results_dir: Path) -> Dict[str, Any]:
    run_files = _load_run_files(results_dir)
    if not run_files:
        return {"error": f"No run*.json files found in {results_dir}"}

    measurement_path = results_dir / "measurements.txt"
    if not measurement_path.exists():
        return {"error": f"Missing measurements.txt in {results_dir}"}

    all_measurements = _parse_all_measurements(measurement_path)
    makespans = []
    slo_ratios = []

    for run_path in run_files:
        pods = _parse_pods(run_path)
        measurements = _slice_measurements(all_measurements, pods)
        makespan = _compute_makespan(pods)
        slo_ratio = _compute_slo_violation_ratio(measurements)
        if makespan is not None:
            makespans.append(makespan)
        if slo_ratio is not None:
            slo_ratios.append(slo_ratio)

    avg_makespan = _mean(makespans)
    avg_slo_ratio = _mean(slo_ratios)
    return {
        "avg_makespan": avg_makespan,
        "avg_slo_ratio": avg_slo_ratio,
        "runs": len(run_files),
    }


def _compute_combined_score(avg_makespan: Optional[float], avg_slo_ratio: Optional[float]) -> float:
    if avg_makespan is None or avg_slo_ratio is None:
        return 0.0
    makespan_score = 1.0 / (1.0 + avg_makespan)
    slo_score = max(0.0, 1.0 - avg_slo_ratio)
    return makespan_score * slo_score


def evaluate(program_path: str) -> EvaluationResult:
    """
    Evaluate the evolved program at "program_path" and return an EvaluationResult
    object containing the evaluation metrics.
    """
    program_file = Path(program_path)
    project_root = Path(__file__).resolve().parents[1]

    if not program_file.exists():
        return EvaluationResult(metrics={"combined_score": 0.0}, artifacts={"error": "Program file not found."})

    try:
        completed = subprocess.run(
            ["bash", str(program_file)],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
        run_log = completed.stdout + completed.stderr
    except subprocess.CalledProcessError as exc:
        run_log = (exc.stdout or "") + (exc.stderr or "")
        return EvaluationResult(
            metrics={"combined_score": 0.0},
            artifacts={"error": "Benchmark run failed.", "log": run_log},
        )

    program_text = program_file.read_text()
    version = _extract_version(program_text)
    results_root = project_root / "openevolve" / "results" / "part3"
    results_dir = (
        results_root / f"version{version}"
        if version
        else _find_latest_results_dir(results_root)
    )

    if results_dir is None or not results_dir.exists():
        return EvaluationResult(
            metrics={"combined_score": 0.0},
            artifacts={"error": "Results directory not found.", "log": run_log},
        )

    eval_summary = _evaluate_results(results_dir)
    if "error" in eval_summary:
        return EvaluationResult(
            metrics={"combined_score": 0.0},
            artifacts={"error": eval_summary["error"], "log": run_log},
        )

    avg_makespan = eval_summary["avg_makespan"]
    avg_slo_ratio = eval_summary["avg_slo_ratio"]
    combined_score = _compute_combined_score(avg_makespan, avg_slo_ratio)

    metrics = {
        "combined_score": combined_score,
        "avg_makespan": avg_makespan or 1e6,
        "avg_slo_ratio": avg_slo_ratio or 1e6,
        "runs": float(eval_summary["runs"]),
    }

    artifacts = {
        "results_dir": str(results_dir),
        "log": run_log,
    }

    return EvaluationResult(metrics=metrics, artifacts=artifacts)
