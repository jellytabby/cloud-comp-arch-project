from __future__ import annotations

import glob
import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from openevolve.evaluation_result import EvaluationResult


LOGGER = logging.getLogger("openevolve.evaluator")


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
) -> tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    starts = [p["cstart"] for p in pods if p["job"] in JOBS and p["cstart"]]
    ends = [p["cend"] for p in pods if p["job"] in JOBS and p["cend"]]
    if not starts or not ends:
        return [], None
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
    if window_measurements:
        return (
            window_measurements,
            {
                "window_start": window_start,
                "window_end": window_end,
                "window_count": len(window_measurements),
                "fallback": False,
            },
        )
    return (
        all_measurements,
        {
            "window_start": window_start,
            "window_end": window_end,
            "window_count": 0,
            "fallback": True,
        },
    )


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


def _load_results_dir_from_latest(
    results_root: Path, project_root: Path
) -> tuple[Optional[Path], Optional[str]]:
    latest_path = results_root / "latest.txt"
    if not latest_path.exists():
        return None, "Missing latest.txt in results directory."
    raw = latest_path.read_text().strip()
    if not raw:
        return None, "latest.txt is empty."
    raw_path = Path(raw)
    candidates: List[Path] = []
    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append(project_root / raw_path)
        candidates.append(results_root / raw_path)
    for candidate in candidates:
        if candidate.exists():
            return candidate, None
    candidates_text = ", ".join(str(c) for c in candidates)
    return None, f"Results directory listed in latest.txt not found. Tried: {candidates_text}"


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
    total_pods = 0
    total_window_measurements = 0

    for run_path in run_files:
        pods = _parse_pods(run_path)
        measurements, window_info = _slice_measurements(all_measurements, pods)
        total_pods += len(pods)
        if window_info:
            total_window_measurements += window_info["window_count"]
            if window_info.get("fallback"):
                if all_measurements:
                    measurement_range = (
                        all_measurements[0]["ts_start"],
                        all_measurements[-1]["ts_end"],
                    )
                else:
                    measurement_range = None
                LOGGER.warning(
                    "[evaluator] No measurements matched job window; using full set. "
                    "window_start=%.0f window_end=%.0f measurement_range=%s pods=%d",
                    window_info["window_start"],
                    window_info["window_end"],
                    measurement_range,
                    len(pods),
                )
        makespan = _compute_makespan(pods)
        slo_ratio = _compute_slo_violation_ratio(measurements)
        if makespan is not None:
            makespans.append(makespan)
        if slo_ratio is not None:
            slo_ratios.append(slo_ratio)

    avg_makespan = _mean(makespans)
    avg_slo_ratio = _mean(slo_ratios)
    if avg_makespan is None:
        return {
            "error": "Failed to compute makespan: no completed job timings found in run files.",
            "pods_parsed": total_pods,
        }
    if avg_slo_ratio is None:
        return {
            "error": "Failed to compute SLO violation ratio: no measurements matched the job windows.",
            "pods_parsed": total_pods,
            "window_measurements": total_window_measurements,
        }
    return {
        "avg_makespan": avg_makespan,
        "avg_slo_ratio": avg_slo_ratio,
        "runs": len(run_files),
    }


def _compute_combined_score(avg_makespan: Optional[float], avg_slo_ratio: Optional[float]) -> float:
    if avg_makespan is None or avg_slo_ratio is None:
        return 0.0
    max_span = 300.0
    makespan_score = max(0.0, 1.0 - (avg_makespan / max_span))
    # slo_score = max(0.0, 1.0 - avg_slo_ratio)
    slo_score = 0.0 if avg_slo_ratio > 0 else 1.0 # strict binary scoring for SLO violations
    return makespan_score * slo_score


def evaluate(program_path: str) -> EvaluationResult:
    """
    Evaluate the evolved program at "program_path" and return an EvaluationResult
    object containing the evaluation metrics.
    """
    program_file = Path(program_path)
    project_root = Path(__file__).resolve().parents[1]

    if not program_file.exists():
        raise FileNotFoundError("Program file not found.")

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
        raise RuntimeError(f"Benchmark run failed.\n{run_log}")

    program_text = program_file.read_text()
    version = _extract_version(program_text)
    results_root = project_root / "openevolve" / "results" / "part3"
    if version:
        results_dir = results_root / f"version{version}"
        latest_error = None
    else:
        results_dir, latest_error = _load_results_dir_from_latest(results_root, project_root)
        if latest_error:
            LOGGER.warning("[evaluator] %s", latest_error)
            return EvaluationResult(
                metrics={"combined_score": 0.0},
                artifacts={
                    "error": latest_error,
                    "log": run_log,
                },
            )

    if results_dir is None or not results_dir.exists():
        raise RuntimeError("Results directory not found.")

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    evolved_copy = results_dir / f"evolved_{timestamp}.sh"
    evolved_copy.write_text(program_text)
    LOGGER.info("[evaluator] saved evolved program: %s", evolved_copy)

    eval_summary = _evaluate_results(results_dir)
    if "error" in eval_summary:
        raise RuntimeError(eval_summary["error"])

    avg_makespan = eval_summary["avg_makespan"]
    avg_slo_ratio = eval_summary["avg_slo_ratio"]
    combined_score = _compute_combined_score(avg_makespan, avg_slo_ratio)
    LOGGER.info(
        "[evaluator] avg_makespan=%.3fs avg_slo_ratio=%.6f combined_score=%.6f",
        avg_makespan,
        avg_slo_ratio,
        combined_score,
    )

    metrics = {
        "combined_score": combined_score,
        "avg_makespan": avg_makespan if avg_makespan is not None else 1e6,
        "avg_slo_ratio": avg_slo_ratio if avg_slo_ratio is not None else 1e6,
        "runs": float(eval_summary["runs"]),
    }

    artifacts = {
        "results_dir": str(results_dir),
        "log": run_log,
    }

    return EvaluationResult(metrics=metrics, artifacts=artifacts)
