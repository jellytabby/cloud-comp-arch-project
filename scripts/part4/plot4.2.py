#!/usr/bin/env python3
"""
Part 4.2 plotting script.
Creates one figure per run (rep1..rep3) with three subplots sharing the same x-axis:
  1) Core occupancy timeline with colored boxes per batch job.
  2) QPS (left axis) and p95 latency (right axis) over time.
  3) Per-core CPU utilization from mpstat.

Usage:
  python3 scripts/part4/plot4.2.py --dir results/part4/2 --output plots/part4/2
"""

import argparse
import os
import re
from datetime import datetime
from typing import Dict, List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

JOB_COLORS = {
    "barnes": "#AACCCA",
    "blackscholes": "#CCA000",
    "canneal": "#CCCCAA",
    "freqmine": "#0CCA00",
    "radix": "#00CCA0",
    "streamcluster": "#CCACCA",
    "vips": "#CC0A00",
    "memcached": "#AAAAAA",
}

BATCH_JOBS = [
    "barnes",
    "blackscholes",
    "canneal",
    "freqmine",
    "radix",
    "streamcluster",
    "vips",
]

LOG_PATTERN = re.compile(r"^(\S+)\s+(\S+)\s+(\S+)\s*(.*)$")
CORES_PATTERN = re.compile(r"\[([0-9,\s]+)\]")


def parse_iso_ts(ts: str) -> float:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts).timestamp()


def parse_cores(args: str) -> List[int]:
    match = CORES_PATTERN.search(args or "")
    if not match:
        return []
    raw = match.group(1)
    cores = []
    for item in raw.split(","):
        item = item.strip()
        if item.isdigit():
            cores.append(int(item))
    return cores


def parse_scheduler_log(path: str) -> Tuple[Dict[int, List[Tuple[float, float, str]]], List[float]]:
    """
    Returns:
      - segments: {core: [(start, end, job_name), ...]}
      - timestamps: list of all event timestamps
    """
    segments: Dict[int, List[Tuple[float, float, str]]] = {}
    timestamps: List[float] = []

    job_state = {}
    paused = {}
    active_start: Dict[Tuple[str, int], float] = {}

    if not os.path.exists(path):
        return segments, timestamps

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("Traceback"):
                continue
            match = LOG_PATTERN.match(line)
            if not match:
                continue
            ts_str, event, job_name, args = match.groups()
            try:
                ts = parse_iso_ts(ts_str)
            except ValueError:
                continue

            timestamps.append(ts)

            if job_name == "scheduler":
                continue

            job_name = job_name.strip()
            cores = parse_cores(args)

            def close_segments(job: str, at: float) -> None:
                current = job_state.get(job, [])
                for core in current:
                    start = active_start.pop((job, core), None)
                    if start is not None:
                        segments.setdefault(core, []).append((start, at, job))

            if event == "start":
                job_state[job_name] = cores
                paused[job_name] = False
                for core in cores:
                    active_start[(job_name, core)] = ts
            elif event == "update_cores":
                if not paused.get(job_name, False):
                    close_segments(job_name, ts)
                job_state[job_name] = cores
                if not paused.get(job_name, False):
                    for core in cores:
                        active_start[(job_name, core)] = ts
            elif event == "pause":
                if not paused.get(job_name, False):
                    close_segments(job_name, ts)
                paused[job_name] = True
            elif event == "unpause":
                paused[job_name] = False
                for core in job_state.get(job_name, []):
                    active_start[(job_name, core)] = ts
            elif event == "end":
                if not paused.get(job_name, False):
                    close_segments(job_name, ts)
                job_state.pop(job_name, None)
                paused.pop(job_name, None)

    return segments, timestamps


def parse_measurements(path: str) -> Tuple[List[float], List[float], List[float]]:
    """
    Returns: (times_s, qps, p95_ms)
    """
    times_s, qps, p95 = [], [], []
    if not os.path.exists(path):
        return times_s, qps, p95

    with open(path, "r") as f:
        for line in f:
            if not line.startswith("read"):
                continue
            parts = line.strip().split()
            if len(parts) < 20:
                continue
            try:
                p95_val = float(parts[12]) / 1000.0
                qps_val = float(parts[16])
                ts_start = int(parts[18]) / 1000.0
            except ValueError:
                continue
            times_s.append(ts_start)
            qps.append(qps_val)
            p95.append(p95_val)
    return times_s, qps, p95


def parse_mpstat(path: str) -> Dict[int, List[Tuple[float, float]]]:
    """
    Returns: {core: [(time_s, util_percent), ...]}
    """
    data: Dict[int, List[Tuple[float, float]]] = {}
    if not os.path.exists(path):
        return data

    with open(path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 12:
                continue
            if not parts[0].isdigit():
                continue
            if parts[2] == "all":
                continue
            try:
                ts = int(parts[0]) / 1000.0
                cpu = int(parts[2])
                idle = float(parts[-1])
                util = 100.0 - idle
            except ValueError:
                continue
            data.setdefault(cpu, []).append((ts, util))
    return data


def get_run_base_time(*series: List[float]) -> float:
    candidates = [min(s) for s in series if s]
    return min(candidates) if candidates else 0.0


def make_plot(run_idx: int, output_dir: str, sched_log: str, measurements: str, mpstat: str) -> None:
    segments, sched_ts = parse_scheduler_log(sched_log)
    meas_t, meas_qps, meas_p95 = parse_measurements(measurements)
    mpstat_data = parse_mpstat(mpstat)

    base_time = get_run_base_time(sched_ts, meas_t, [t for core in mpstat_data for t, _ in mpstat_data[core]])

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True, gridspec_kw={"height_ratios": [1.2, 1, 1]})

    # Subplot 1: core occupancy
    ax0 = axes[0]
    all_cores = sorted(segments.keys())
    if not all_cores:
        all_cores = sorted(mpstat_data.keys())
    for core in all_cores:
        for start, end, job in segments.get(core, []):
            x0 = start - base_time
            width = max(0.0, end - start)
            color = JOB_COLORS.get(job, "#999999")
            rect = mpatches.Rectangle((x0, core - 0.4), width, 0.8, color=color, alpha=0.9)
            ax0.add_patch(rect)
    ax0.set_ylabel("Core")
    ax0.set_yticks(all_cores if all_cores else [0])
    ax0.set_title(f"Run {run_idx}: Batch job scheduling timeline")
    legend_handles = [mpatches.Patch(color=JOB_COLORS[j], label=j) for j in BATCH_JOBS if j in JOB_COLORS]
    ax0.legend(handles=legend_handles, ncol=4, fontsize=7, loc="upper right")

    # Subplot 2: QPS and p95 latency
    ax1 = axes[1]
    if meas_t:
        times = [t - base_time for t in meas_t]
        ax1.plot(times, meas_qps, color="#4A90D9", label="QPS")
        ax1.set_ylabel("QPS")
        ax1b = ax1.twinx()
        ax1b.plot(times, meas_p95, color="#D94A4A", label="p95 latency")
        ax1b.set_ylabel("p95 latency (ms)")
        ax1.axhline(0.0, color="#CCCCCC", linewidth=0.5)
        # build combined legend
        lines, labels = ax1.get_legend_handles_labels()
        lines2, labels2 = ax1b.get_legend_handles_labels()
        ax1.legend(lines + lines2, labels + labels2, loc="upper right", fontsize=8)
    ax1.set_title("QPS and p95 latency")

    # Subplot 3: CPU utilization per core
    ax2 = axes[2]
    for core, series in mpstat_data.items():
        xs = [t - base_time for t, _ in series]
        ys = [v for _, v in series]
        ax2.plot(xs, ys, label=f"core {core}")
    ax2.set_ylabel("CPU util (%)")
    ax2.set_xlabel("Time since run start (s)")
    if mpstat_data:
        ax2.legend(ncol=4, fontsize=7, loc="upper right")
    ax2.set_title("Per-core CPU utilization")

    for ax in axes:
        ax.grid(True, linestyle=":", alpha=0.4)

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"run{run_idx}.pdf")
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close(fig)
    print(f"Saved {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot Part 4.2 results")
    parser.add_argument("--dir", default="results/part4/2", help="Results directory")
    parser.add_argument("--output", default="plots/part4/2", help="Output directory")
    args = parser.parse_args()

    for run_idx in range(1, 4):
        sched_log = os.path.join(args.dir, f"scheduler_log_rep{run_idx}.txt")
        measurements = os.path.join(args.dir, f"measurements_rep{run_idx}.txt")
        mpstat = os.path.join(args.dir, f"mpstat_run{run_idx}.txt")
        if not any(os.path.exists(p) for p in (sched_log, measurements, mpstat)):
            print(f"Run {run_idx}: no files found, skipping")
            continue
        make_plot(run_idx, args.output, sched_log, measurements, mpstat)


if __name__ == "__main__":
    main()
