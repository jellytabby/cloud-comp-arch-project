import os
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

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

def parse_ts(ts):
    if not ts:
        return None
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(ts).timestamp()
    except ValueError:
        return None

def parse_container_inspect(filepath):
    if not os.path.exists(filepath):
        return {}
    with open(filepath, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Failed to parse JSON from {filepath}")
            return {}


    job_times = {}
    for entry in data:
        name = entry.get("Name", "").lstrip("/")
        state = entry.get("State", {})
        started_at = parse_ts(state.get("StartedAt"))
        finished_at = parse_ts(state.get("FinishedAt"))
        if name:
            job_times[name] = {
                "start": started_at,
                "end": finished_at,
            }

    return job_times

def parse_measurements(filepath):
    INTERVAL = 15.0  # seconds
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    measurements = []
    start = None
    interval_ms = int(INTERVAL * 1000)
    for line in lines:
        if line.startswith("Timestamp start:"):
            start = int(line.split(": ", 1)[1].strip())
        if line.startswith("read"):
            assert start is not None, "Timestamp start must be defined before measurements"
            parts = line.strip().split()
            try:
                p95 = float(parts[12]) / 1000.0  # ms
                qps = float(parts[16])
                target = int(parts[17])
                idx = len(measurements)
                ts_start = start + (interval_ms * idx)
                ts_end = ts_start + interval_ms
                measurements.append({
                    "p95": p95,
                    "qps": qps,
                    "target": target,
                    "ts_start": ts_start,
                    "ts_end": ts_end,
                })
            except (IndexError, ValueError):
                continue
    return measurements

def parse_mpstat(filepath):
    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found.")
        return {}
    with open(filepath, 'r') as f:
        lines = f.readlines()

    samples: Dict[int, List[Optional[float]]] = {}
    i = 0
    while i < len(lines):
        parts = lines[i].strip().split()
        if len(parts) > 3 and parts[2] == "CPU" and parts[3] == "%usr":
            ts = int(parts[0])
            samples[ts] = [None, None, None, None]
            for j in range(i + 1, min(i + 10, len(lines))):
                sample_parts = lines[j].strip().split()
                if len(sample_parts) < 4 or not sample_parts[2].isdigit():
                    continue
                cpu_id = int(sample_parts[2])
                if cpu_id < 0 or cpu_id > 3:
                    continue
                try:
                    usr = float(sample_parts[3])
                except ValueError:
                    continue
                samples[ts][cpu_id] = usr
            i += 10
            continue
        i += 1

    cleaned = {ts: vals for ts, vals in samples.items() if all(v is not None for v in vals)}
    return cleaned

def read_scheduler_logs(filepath):
    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found.")
        return {}

    results = {}
    with open(filepath, 'r') as f:
        for line in f:
            splits = line.strip().split()
            if len(splits) >= 4 and splits[1] == "update_cores":
                # expected format: TIMESTAMP update_cores JOBNAME [core_list]
                ts_str = splits[0]
                job = splits[2]
                cores_raw = " ".join(splits[3:]).strip()
                # cores_raw should look like: [3] or [0,1]
                cores = []
                if cores_raw.startswith("[") and cores_raw.endswith("]"):
                    inner = cores_raw[1:-1].strip()
                    if inner:
                        for part in inner.split(','):
                            try:
                                cores.append(int(part.strip()))
                            except ValueError:
                                continue

                # parse timestamp to epoch seconds (assume UTC if no tz)
                try:
                    dt = datetime.fromisoformat(ts_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    ts = dt.timestamp()
                except ValueError:
                    ts = None

                results[ts] = {
                    "job": job,
                    "cores": cores,
                }
    return results






def build_plot(
    output_dir: str,
    run_idx: int,
    job_times: dict,
    measurements: list,
    cpu_samples: dict,
    logger_data: dict,
    qps_ylim: Optional[float],
    p95_ylim: Optional[float],
) -> None:
    if not job_times and not measurements and not cpu_samples:
        print(f"Run {run_idx}: no data found, skipping")
        return

    job_starts = [v["start"] for v in job_times.values() if v.get("start")]
    meas_times = [m["ts_start"] / 1000.0 for m in measurements]
    cpu_times = [ts / 1000.0 for ts in cpu_samples.keys()]
    base_time = min(job_starts + meas_times + cpu_times) if (job_starts or meas_times or cpu_times) else 0.0
    end_time_candidates = []
    end_time_candidates += [v["end"] for v in job_times.values() if v.get("end")]
    end_time_candidates += [m["ts_end"] / 1000.0 for m in measurements if m.get("ts_end")]
    end_time_candidates += [ts / 1000.0 for ts in cpu_samples.keys()]
    end_time = max(end_time_candidates) if end_time_candidates else base_time

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True, gridspec_kw={"height_ratios": [1, 1, 1]})

    # Subplot 1: batch job timeline (stacked by job)
    # ax0 = axes[0]
    # bar_h = 0.8
    # gap = 0.3
    # for idx, job in enumerate(BATCH_JOBS):
    #     if job not in job_times:
    #         continue
    #     start = job_times[job].get("start")
    #     end = job_times[job].get("end")
    #     if start is None or end is None:
    #         continue
    #     x0 = start - base_time
    #     width = max(0.0, end - start)
    #     y0 = idx * (bar_h + gap)
    #     rect = mpatches.Rectangle((x0, y0), width, bar_h, color=JOB_COLORS.get(job, "#999999"), alpha=0.9)
    #     ax0.add_patch(rect)
    # ax0.set_yticks([i * (bar_h + gap) + bar_h / 2 for i in range(len(BATCH_JOBS))])
    # ax0.set_yticklabels(BATCH_JOBS)
    # ax0.set_ylabel("Batch jobs")
    # ax0.set_title(f"Run {run_idx}: Batch job scheduling timeline")
    # legend_handles = [mpatches.Patch(color=JOB_COLORS[j], label=j) for j in BATCH_JOBS if j in JOB_COLORS]
    # ax0.legend(handles=legend_handles, ncol=1, fontsize=7,
    #            loc="upper right", framealpha=0.95,
    #            handlelength=1.2, handletextpad=0.4, borderpad=0.4)

    # Subplot 1: core timeline (pointwise measurements -> short horizontal ticks)
    ax0 = axes[0]
    if logger_data:
        # logger_data keys are epoch seconds; align to base_time to get relative x
        entries = sorted(((ts, e) for ts, e in logger_data.items() if ts is not None), key=lambda x: x[0])
        span = max(1.0, end_time - base_time)
        # tick width scales with span but stays visible for short runs
        tick_width = min(2.0, max(0.1, span * 0.002))
        # determine max core index seen
        seen_cores = [core for _, e in entries for core in e.get("cores", [])]
        max_core = int(max(seen_cores)) if seen_cores else 3
        bar_h = 0.9
        for ts, entry in entries:
            x = ts - base_time
            job = entry.get("job")
            cores = entry.get("cores", [])
            color = JOB_COLORS.get(job, "#999999")
            for core in cores:
                # draw a filled rectangle centered vertically on the core index
                rect = mpatches.Rectangle((x - tick_width / 2.0, core - bar_h / 2.0),
                                          tick_width, bar_h,
                                          color=color, alpha=0.9)
                ax0.add_patch(rect)
        ax0.set_yticks(list(range(max_core + 1)))
        ax0.set_yticklabels([f"core {i}" for i in range(max_core + 1)])
        ax0.set_ylim(-0.5, max_core + 0.5)
    ax0.set_ylabel("CPU cores")
    ax0.set_title(f"Run {run_idx}: Scheduler core assignments over time")
    legend_handles = [mpatches.Patch(color=JOB_COLORS[j], label=j) for j in BATCH_JOBS if j in JOB_COLORS]
    ax0.legend(handles=legend_handles, ncol=1, fontsize=7,
               loc="upper right", framealpha=0.95,
               handlelength=1.2, handletextpad=0.4, borderpad=0.4)

    # Subplot 2: QPS + p95
    ax1 = axes[1]
    if measurements:
        times = [m["ts_start"] / 1000.0 - base_time for m in measurements]
        widths = [(m["ts_end"] - m["ts_start"]) / 1000.0 for m in measurements]
        qps = [m["qps"] for m in measurements]
        p95 = [m["p95"] for m in measurements]
        print(f"Run {run_idx}: Found {len(measurements)} measurement points")
        ax1.bar(times, qps, width=widths, align="edge", color="#4A90D9", alpha=0.8, label="QPS")
        ax1.set_ylabel("QPS")
        if qps_ylim is not None:
            ax1.set_ylim(0.0, qps_ylim)
        ax1b = ax1.twinx()
        ax1b.plot(times, p95, color="#D94A4A", label="p95 latency")
        ax1b.axhline(0.8, color="#D94A4A", linestyle="--", linewidth=0.8, alpha=0.7)
        ax1b.set_ylabel("p95 latency (ms)")
        if p95_ylim is not None:
            ax1b.set_ylim(0.0, p95_ylim)
        lines, labels = ax1.get_legend_handles_labels()
        lines2, labels2 = ax1b.get_legend_handles_labels()
        ax1.legend(lines + lines2, labels + labels2, loc="upper right", fontsize=8)
    ax1.set_title("QPS and p95 latency")

    # Subplot 3: CPU usr utilization per core
    ax2 = axes[2]
    if cpu_samples:
        sorted_samples = sorted(cpu_samples.items())
        times = [(ts / 1000.0) - base_time for ts, _ in sorted_samples]
        per_core = list(zip(*[vals for _, vals in sorted_samples]))
        for core_idx, series in enumerate(per_core):
            ax2.plot(times, series, label=f"core {core_idx}")
        ax2.legend(ncol=4, fontsize=7, loc="upper right")
    ax2.set_ylabel("CPU %usr")
    ax2.set_xlabel("Time since run start (s)")
    ax2.set_title("Per-core CPU utilization")

    for ax in axes:
        ax.grid(True, linestyle=":", alpha=0.4)
        ax.set_xlim(left=0.0, right=max(0.0, end_time - base_time))

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"run{run_idx}.pdf")
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close(fig)
    print(f"Saved {output_path}")


def compute_job_durations(job_times: dict) -> Dict[str, float]:
    durations = {}
    for job, times in job_times.items():
        start = times.get("start")
        end = times.get("end")
        if start is None or end is None:
            continue
        durations[job] = end - start
    return durations


def compute_makespan(job_times: dict) -> Optional[float]:
    starts = [v.get("start") for v in job_times.values() if v.get("start")]
    ends = [v.get("end") for v in job_times.values() if v.get("end")]
    if not starts or not ends:
        return None
    return max(ends) - min(starts)


def compute_slo_violation_ratio(measurements: list, job_times: dict, threshold_ms: float = 0.8) -> Optional[float]:
    if not measurements or not job_times:
        return None
    starts = [v.get("start") for v in job_times.values() if v.get("start")]
    ends = [v.get("end") for v in job_times.values() if v.get("end")]
    if not starts or not ends:
        return None
    window_start = min(starts)
    window_end = max(ends)
    windowed = [m for m in measurements if (m.get("ts_start", 0) / 1000.0) >= window_start and (m.get("ts_end", 0) / 1000.0) <= window_end]
    if not windowed:
        return None
    violations = sum(1 for m in windowed if m.get("p95", 0) > threshold_ms)
    return violations / len(windowed)


def latex_table(all_durations: List[Dict[str, float]], all_makespans: List[Optional[float]]) -> str:
    lines = [
        r"\begin{center}",
        r"\begin{tabular}{ |c|c|c| }",
        r"\hline",
        r"\textbf{job name} & \textbf{mean time [s]} & \textbf{std [s]} \\",
        r"\hline\hline",
    ]
    for job in BATCH_JOBS:
        vals = [d[job] for d in all_durations if job in d]
        if vals:
            lines.append(rf"{job} & {sum(vals) / len(vals):.1f} & {0.0 if len(vals) == 1 else (sum((v - sum(vals)/len(vals))**2 for v in vals) / len(vals))**0.5:.1f} \\  \hline")
        else:
            lines.append(rf"{job} & -- & -- \\  \hline")

    valid_ms = [m for m in all_makespans if m is not None]
    if valid_ms:
        mean_ms = sum(valid_ms) / len(valid_ms)
        std_ms = 0.0 if len(valid_ms) == 1 else (sum((v - mean_ms) ** 2 for v in valid_ms) / len(valid_ms)) ** 0.5
        lines.append(rf"total time & {mean_ms:.1f} & {std_ms:.1f} \\  \hline")
    else:
        lines.append(r"total time & -- & -- \\  \hline")

    lines += [r"\end{tabular}", r"\end{center}", ""]
    return "\n".join(lines)

                
if __name__ == "__main__":
    base_dir = "results/part4/2/version_11"
    output_dir = "plots/part4/2/version_11"
    all_durations = []
    all_makespans = []
    slo_ratios = []
    runs = []
    all_qps = []
    all_p95 = []
    for run_idx in (1, 3, 5):
        job_times = parse_container_inspect(os.path.join(base_dir, f"container_inspect_{run_idx}.txt"))
        measurements = parse_measurements(os.path.join(base_dir, f"measurements_rep{run_idx}.txt"))
        cpu_samples = parse_mpstat(os.path.join(base_dir, f"mpstat_run{run_idx}.txt"))
        logger_data = read_scheduler_logs(os.path.join(base_dir, f"scheduler_log_rep{run_idx}.txt"))
        runs.append((run_idx, job_times, measurements, cpu_samples, logger_data))
        all_qps.extend([m["qps"] for m in measurements if m.get("qps") is not None])
        all_p95.extend([m["p95"] for m in measurements if m.get("p95") is not None])

    qps_ylim = max(all_qps) * 1.05 if all_qps else None
    p95_ylim = max(all_p95) * 1.05 if all_p95 else None

    for run_idx, job_times, measurements, cpu_samples, logger_data in runs:
        build_plot(output_dir, run_idx, job_times, measurements, cpu_samples, logger_data, qps_ylim, p95_ylim)
        durations = compute_job_durations(job_times)
        makespan = compute_makespan(job_times)
        slo_ratio = compute_slo_violation_ratio(measurements, job_times)
        all_durations.append(durations)
        all_makespans.append(makespan)
        slo_ratios.append(slo_ratio)

    print("\n" + "=" * 60)
    print(latex_table(all_durations, all_makespans))
    print("% SLO violation ratios (p95 > 0.8 ms)")
    for i, ratio in enumerate(slo_ratios, 1):
        print(f"% Run {i}: {ratio * 100:.1f}% violations" if ratio is not None else f"% Run {i}: N/A")
    print("=" * 60)