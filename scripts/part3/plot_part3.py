#!/usr/bin/env python3
"""
Part 3 analysis script.
Usage:
    python3 analyze_part3.py \
        --dir results/ \
        --measurements measurements.txt \
        --output plots/
 
  --dir          Directory containing run1.json, run2.json, run3.json
                 (kubectl get pods -o json output, one file per run).
  --measurements Single mcperf measurement file covering all runs.
                 Intervals are automatically sliced per run based on each
                 run's batch window (first batch container start ->
                 last batch container end).
  --output       Directory for plots and LaTeX output (default: .)
 
Outputs:
  - <output>/run{1,2,3}_latency.pdf   bar plots of p95 latency over time
  - <output>/latex_table.tex          LaTeX source for the results table
"""
 
import argparse
import glob
import json
import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime
 
# ── Job colours (matching the template's main.tex) ───────────────────────────
JOB_COLORS = {
    "barnes":        "#AACCCA",
    "blackscholes":  "#CCA000",
    "canneal":       "#CCCCAA",
    "freqmine":      "#0CCA00",
    "radix":         "#00CCA0",
    "streamcluster": "#CCACCA",
    "vips":          "#CC0A00",
    # "memcached":     "#AAAAAA",
}

NODE_HATCHES = {
    "node-a-8core": "/",
    "node-b-4core": "+",
}


JOBS = ["barnes", "blackscholes", "canneal", "freqmine",
        "radix", "streamcluster", "vips"]
 
 
# ── Parsing ───────────────────────────────────────────────────────────────────
 
def parse_all_measurements(path):
    """
    Parse a single mcperf file (raw TSV or JSON-wrapped stdout).
    Returns a list of dicts sorted by ts_start:
        p95      float  ms
        ts_start int    unix ms
        ts_end   int    unix ms
    Column layout (0-indexed):
        0=type 1=avg 2=std 3=min 4=p5 5=p10 6=p50 7=p67 8=p75
        9=p80 10=p85 11=p90 12=p95 13=p99 14=p999 15=p9999
        16=QPS 17=target 18=ts_start 19=ts_end
    p95 is in µs; timestamps are unix milliseconds.
    """
    with open(path) as f:
        raw = f.read().strip()
 
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 20:
            continue
        try:
            rows.append({
                "p95":      float(parts[12]) / 1000.0,  # µs -> ms
                "ts_start": int(parts[18]),              # unix ms
                "ts_end":   int(parts[19]),              # unix ms
            })
        except (ValueError, IndexError):
            continue
 
    rows.sort(key=lambda r: r["ts_start"])
    return rows
 
 
def slice_measurements(all_measurements, pods):
    """
    Return the subset of measurements whose interval falls within the
    batch window of this run: [first batch cstart, last batch cend].
    Pod times are unix seconds; measurement timestamps are unix ms.
    """
    starts = [p["cstart"] for p in pods if p["job"] in JOBS and p["cstart"]]
    ends   = [p["cend"]   for p in pods if p["job"] in JOBS and p["cend"]]
    if not starts or not ends:
        return []
    window_start = min(starts) * 1e3   # s -> ms
    window_end   = max(ends)   * 1e3
    print(f"  Batch window: {window_start/1e3:.1f}s to {window_end/1e3:.1f}s ")
    window_measurements = []
    for m in all_measurements:
        if m["ts_start"] >= window_start and m["ts_end"] <= window_end:
            window_measurements.append(m)
        elif m["ts_start"] <= window_start and m["ts_end"] > window_start:
            # Include intervals that start before the window but end after it starts
            window_measurements.append(m)
        elif m["ts_start"] <= window_end and m["ts_end"] > window_end:
            # Include intervals that start before the window ends but end after it
            window_measurements.append(m)
    print(f"  Found {len(window_measurements)} measurement intervals within batch window")
    print(f" Start: {window_measurements[0]['ts_start']/1e3:.1f}s, End: {window_measurements[-1]['ts_end']/1e3:.1f}s")
    return window_measurements
 
 
def parse_pods(path):
    """
    Parse kubectl get pods -o json.
    Returns list of dicts: job, node, cstart (unix s), cend (unix s).
    """
    with open(path) as f:
        data = json.load(f)
 
    def parse_dt(s):
        if not s:
            return None
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
 
    pods = []
    for item in data["items"]:
        name = item['status']['containerStatuses'][0]['name'][7:]  # strip "parsec-"
        node = item.get("spec", {}).get("nodeName", "unknown")[:-5]
        print(f"Pod: {name} on {node}")
 
        cs = item.get("status", {}).get("containerStatuses", [])
        if not cs:
            continue
        state = cs[0].get("state", {})
        term  = state.get("terminated", {})
        run_s = state.get("running", {})
 
        cstart = parse_dt(term.get("startedAt") or run_s.get("startedAt"))
        cend   = parse_dt(term.get("finishedAt"))
 
        if name in JOBS:
            pods.append({"job": name, "node": node, "cstart": cstart, "cend": cend})
    return pods

    # time_format = '%Y-%m-%dT%H:%M:%SZ'
    # start_times = []
    # completion_times = []
    # for item in json_file['items']:
    #     name = item['status']['containerStatuses'][0]['name']
    #     print("Job: ", str(name))
    #     if str(name) != "memcached":
    #         try:
    #             start_time = datetime.strptime(
    #                     item['status']['containerStatuses'][0]['state']['terminated']['startedAt'],
    #                     time_format)
    #             completion_time = datetime.strptime(
    #                     item['status']['containerStatuses'][0]['state']['terminated']['finishedAt'],
    #                     time_format)
    #             print("Job time: ", completion_time - start_time)
    #             start_times.append(start_time)
    #             completion_times.append(completion_time)
    #         except KeyError:
    #             print("Job {0} has not completed....".format(name))
    #             sys.exit(0)

    # if len(start_times) != 7 and len(completion_times) != 7:
    #     print("You haven't run all the PARSEC jobs. Exiting...")
    #     sys.exit(0)
    
    # print("Total time: {0}".format(max(completion_times) - min(start_times)))
    # file.close()
 


 
 
# ── Per-run stats ─────────────────────────────────────────────────────────────
 
def compute_job_durations(pods):
    return {p["job"]: p["cend"] - p["cstart"]
            for p in pods if p["job"] in JOBS and p["cstart"] and p["cend"]}
 
 
def compute_makespan(pods):
    starts = [p["cstart"] for p in pods if p["job"] in JOBS and p["cstart"]]
    ends   = [p["cend"]   for p in pods if p["job"] in JOBS and p["cend"]]
    return (max(ends) - min(starts)) if (starts and ends) else None
 
 
def compute_slo_violation_ratio(measurements):
    """Fraction of measurement intervals where p95 > 1 ms."""
    if not measurements:
        return None
    violations = sum(1 for m in measurements if m["p95"] > 1.0)
    return violations / len(measurements)
 
 
# ── Plot ──────────────────────────────────────────────────────────────────────
 
def make_plot(run_idx, measurements, pods, output_path):
    """
    Bar chart: each bar width = mcperf interval duration,
    height = p95 latency. Job annotation bars drawn above the axis,
    grouped by node, colour-coded per the template.
    x=0 is the start of the first batch container.
    """
    batch_starts = [p["cstart"] for p in pods if p["job"] in JOBS and p["cstart"]]
    if not batch_starts:
        print(f"  [warn] no batch pods for run {run_idx}, skipping plot")
        return
 
    t0 = min(batch_starts)   # unix seconds

    xs      = [m["ts_start"] / 1e3 - t0 for m in measurements]
    widths  = [(m["ts_end"] - m["ts_start"]) / 1e3 for m in measurements]
    heights = [m["p95"] for m in measurements]
 
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.bar(xs, heights, width=widths, align="edge",
           color="#4A90D9", alpha=0.99, zorder=10)
    ax.axhline(1.0, color="red", linewidth=1.2, linestyle="--",
               label="SLO 1 ms", zorder=3)
    ax.grid(axis="y", linestyle=":", alpha=0.4, zorder=1)
 
    # ── Job annotation bars above the plot ───────────────────────────────────
    # nodes    = sorted(set(p["node"] for p in pods if p["job"] in JOBS))
    # node_row = {n: i for i, n in enumerate(nodes)}
    # n_nodes  = max(1, len(nodes))
    ymax     = 0.4
    bar_h    = ymax * 0.09
    gap      = ymax * 0.025
 
    for p in pods:
        if p["job"] not in JOBS or not (p["cstart"] and p["cend"]):
            continue
        index = JOBS.index(p["job"]) + 1
        x0  = p["cstart"] - t0
        x1  = p["cend"]   - t0
        # row = node_row.get(p["node"], 0)
        y1  = ymax + index * (bar_h + gap)
        zlevel = len(pods) - index  # ensure bars are above the grid and main bars
        col = JOB_COLORS[p["job"]]
        hatch = NODE_HATCHES.get(p["node"], None)
 
        # ax.add_patch(mpatches.FancyBboxPatch(
        #     (x0, y0), x1 - x0, bar_h,
        #     boxstyle="round,pad=0.5", linewidth=0.4,
        #     edgecolor="white", facecolor=col, alpha=0.92,
        #     transform=ax.transData, clip_on=False))
        ax.add_patch(mpatches.Rectangle(
            (x0, 0.0), x1 - x0, y1,
            linewidth=0.4, edgecolor="white", facecolor=col, alpha=0.92,
            hatch=hatch, transform=ax.transData, clip_on=False, zorder=zlevel))
 
        # ax.text((x0 + x1) / 2, y0 + bar_h / 2,
        #         p["job"][:3].upper(),
        #         ha="center", va="center", fontsize=6.5,
        #         color="white", fontweight="bold",
        #         transform=ax.transData, clip_on=False)
 
    # Node labels to the right of the annotation bars
    # ax_h = ymax + gap + n_nodes * (bar_h + gap)
    # for node, row in node_row.items():
    #     y_centre = ymax + gap + row * (bar_h + gap) + bar_h / 2
    #     # strip the random suffix (last token after final '-')
    #     short = "-".join(node.split("-")[:-1]) if "-" in node else node
    #     ax.text(1.003, y_centre / ax_h, short,
    #             transform=ax.transAxes, fontsize=7,
    #             va="center", color="#444")
    ax.set_xlabel("Time since first batch job start [s]", fontsize=10)
    ax.set_ylabel("p95 latency [ms]", fontsize=10)
    ax.set_title(f"Run {run_idx}: Memcached p95 latency with batch job annotations",
                 fontsize=11)
    # ax.set_xlim(left=min(xs) if xs else 0, right=max(xs)+widths[-1]+1 if xs else 0)
    ax.set_ylim(bottom=0, ymax=1.05)
    last_meas_end = max(xs) + widths[-1] if xs else 0
    last_job_end  = max(p["cend"] - t0 for p in pods 
                    if p["job"] in JOBS and p["cend"])
    ax.set_xlim(left=min(xs) if xs else 0, 
            right=max(last_meas_end, last_job_end) + 5)

    handles = [mpatches.Patch(color=JOB_COLORS[p["job"]], label=p["job"], hatch=NODE_HATCHES.get(p["node"], None)) for p in pods if p["job"] in JOBS]
    # handles = [mpatches.Patch(color="#000000", label="Node A (8-core)", hatch="/"),
    #            mpatches.Patch(color="#000000", label="Node B (4-core)", hatch=NODE_HATCHES["node-b-4core"])]
    handles += [
        plt.Line2D([0], [0], color="red", linestyle="--", label="SLO 1 ms"),
        mpatches.Patch(color="#4A90D9", alpha=0.75, label="p95 latency - memcached", hatch=NODE_HATCHES["node-b-4core"]),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=7.5,
              ncol=3, framealpha=0.95)
 
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved → {output_path}")
 
 
# ── LaTeX ─────────────────────────────────────────────────────────────────────
 
def latex_table(all_durations, all_makespans, all_slo_ratios):
    lines = [
        r"\begin{center}",
        r"\begin{tabular}{ |c|c|c| }",
        r"\hline",
        r"\textbf{job name} & \textbf{mean time [s]} & \textbf{std [s]} \\",
        r"\hline\hline",
    ]
    for job in JOBS:
        vals = [d[job] for d in all_durations if job in d]
        if vals:
            lines.append(rf"{job} & {np.mean(vals):.1f} & {np.std(vals):.1f} \\  \hline")
        else:
            lines.append(rf"{job} & -- & -- \\  \hline")
 
    valid_ms = [m for m in all_makespans if m is not None]
    if valid_ms:
        lines.append(
            rf"total time & {np.mean(valid_ms):.1f} & {np.std(valid_ms):.1f} \\  \hline")
    else:
        lines.append(r"total time & -- & -- \\  \hline")
 
    lines += [r"\end{tabular}", r"\end{center}", ""]
    lines.append("% SLO violation ratios (p95 > 1 ms, during batch window only)")
    for i, r in enumerate(all_slo_ratios, 1):
        lines.append(f"% Run {i}: " +
                     (f"{r*100:.1f}% violations" if r is not None else "N/A"))
    return "\n".join(lines)
 
 
# ── Main ──────────────────────────────────────────────────────────────────────
 
def main():
    parser = argparse.ArgumentParser(description="Part 3 analysis script")
    parser.add_argument("--dir", required=True,
                        help="Directory containing run1.json, run2.json, run3.json")
    parser.add_argument("--measurements", required=True,
                        help="Single mcperf measurement file covering all runs")
    parser.add_argument("--output", default="plots/part3/version3/",
                        help="Output directory (default: plots/part3/)")
    args = parser.parse_args()
 
    # Discover run JSON files
    run_files = sorted(glob.glob(os.path.join(args.dir, "run*.json")))
    if not run_files:
        print(f"ERROR: no run*.json files found in {args.dir}")
        sys.exit(1)
    print(f"Found {len(run_files)} run file(s): {[os.path.basename(f) for f in run_files]}")
 
    os.makedirs(args.output, exist_ok=True)
 
    # Load the single measurement file once
    all_measurements = parse_all_measurements(args.measurements)
    print(f"Loaded {len(all_measurements)} measurement intervals from {args.measurements}")
 
    all_durations  = []
    all_makespans  = []
    all_slo_ratios = []
 
    for i, run_path in enumerate(run_files, 1):
        print(f"\n── Run {i}  ({os.path.basename(run_path)}) ──────────────────")
 
        pods = parse_pods(run_path)
        measurements = slice_measurements(all_measurements, pods)
 
        print(f"  Pods:         {[p['job'] for p in pods]}")
        print(f"  Measurements: {len(measurements)} intervals in batch window")
 
        durations = compute_job_durations(pods)
        makespan  = compute_makespan(pods)
        slo_ratio = compute_slo_violation_ratio(measurements)
 
        for job, dur in sorted(durations.items()):
            print(f"    {job:15s}: {dur:.1f}s")
        print(f"  Makespan:      {makespan:.1f}s" if makespan else "  Makespan:      N/A")
        print(f"  SLO violation: {slo_ratio*100:.1f}%" if slo_ratio is not None else "  SLO violation: N/A")
 
        all_durations.append(durations)
        all_makespans.append(makespan)
        all_slo_ratios.append(slo_ratio)
 
        make_plot(i, measurements, pods,
                  os.path.join(args.output, f"run{i}_latency.svg"))
 
    tex = latex_table(all_durations, all_makespans, all_slo_ratios)
    # tex_path = os.path.join(args.output, "latex_table.tex")
    # with open(tex_path, "w") as f:
    #     f.write(tex)
 
    # print(f"\n── LaTeX saved → {tex_path}")
    print("\n" + "=" * 60)
    print(tex)
    print("=" * 60)
 
 
if __name__ == "__main__":
    main()