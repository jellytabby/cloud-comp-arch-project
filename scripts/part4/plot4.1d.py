import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

RESULTS_DIR = "results/part4/1d"
OUTPUT_PLOT_PREFIX = "plots/part4/1d/latency_cpu_vs_qps_C"

os.makedirs(os.path.dirname(OUTPUT_PLOT_PREFIX), exist_ok=True)

def parse_mpstat(filepath):
    """
    Parses mpstat output and returns a list of (timestamp_ms, cpu_util_percent)
    where cpu_util_percent = (100.0 - idle) * 4.
    """
    mpstat_data = []
    with open(filepath, "r") as f:
        for line in f:
            if "all" in line:
                parts = line.strip().split()
                if len(parts) >= 12 and parts[0].isdigit():
                    try:
                        ts = int(parts[0])
                        idle = float(parts[-1]) # %idle is the last column
                        util = (100.0 - idle) * 4.0
                        mpstat_data.append((ts, util))
                    except ValueError:
                        continue
    return sorted(mpstat_data)

def get_cpu_util_for_interval(mpstat_data, ts_start, ts_end):
    """
    Finds the average CPU utilization in the given interval.
    If no points fall exactly in the interval, finds the closest point,
    or takes points covering it.
    """
    utils = [util for (ts, util) in mpstat_data if ts_start <= ts <= ts_end]
    if not utils:
        # Fallback if the interval is too small or misses the mpstat tick
        # Just find the closest timestamp
        if not mpstat_data:
            return 0.0
        closest_util = min(mpstat_data, key=lambda x: min(abs(x[0]-ts_start), abs(x[0]-ts_end)))[1]
        return closest_util
    return np.mean(utils)

def load_data(t, c):
    """
    Returns a dict mapping target_qps -> list of (achieved_qps, p95_latency, avg_cpu_util) across reps
    """
    data = {}
    for rep in range(1, 4):
        meas_file = os.path.join(RESULTS_DIR, f"measurements_T{t}_C{c}_rep{rep}.txt")
        mpstat_file = os.path.join(RESULTS_DIR, f"mpstat_T{t}_C{c}_rep{rep}.txt")
        
        if not os.path.exists(meas_file) or not os.path.exists(mpstat_file):
            print(f"Warning: Missing files for T={t}, C={c}, Rep={rep}")
            continue
            
        mpstat_data = parse_mpstat(mpstat_file)
        
        with open(meas_file, "r") as f:
            for line in f:
                if line.startswith("read"):
                    parts = line.strip().split()
                    try:
                        p95 = float(parts[12]) / 1000.0  # ms
                        qps = float(parts[16])
                        target = int(parts[17])
                        ts_start = int(parts[18])
                        ts_end = int(parts[19])
                    except (IndexError, ValueError):
                        continue
                    
                    cpu_util = get_cpu_util_for_interval(mpstat_data, ts_start, ts_end)
                    
                    if target not in data:
                        data[target] = []
                    data[target].append((qps, p95, cpu_util))
    return data

def main():
    t = 3
    
    # Calculate global max latency to keep left y-axis consistent across all plots
    global_max_p95 = 0
    all_data = {}
    for c in [1, 2, 3]:
        data = load_data(t, c)
        if data:
            all_data[c] = data
            for tgt, vals in data.items():
                p95_vals = [d[1] for d in vals]
                global_max_p95 = max(global_max_p95, np.mean(p95_vals))
                
    # Add a little headroom
    global_max_p95 *= 1.2

    for c in [1, 2, 3]:
        if c not in all_data:
            print(f"Skipping C={c}, no data.")
            continue
            
        data = all_data[c]
            
        targets = sorted(data.keys())
        mean_qps = []
        mean_p95 = []
        mean_cpu = []
        
        for tgt in targets:
            qps_vals = [d[0] for d in data[tgt]]
            p95_vals = [d[1] for d in data[tgt]]
            cpu_vals = [d[2] for d in data[tgt]]
            
            mean_qps.append(np.mean(qps_vals))
            mean_p95.append(np.mean(p95_vals))
            mean_cpu.append(np.mean(cpu_vals))
            
        fig, ax1 = plt.subplots(figsize=(8, 6))
        
        # Plot p95 latency on left y-axis
        color1 = 'tab:blue'
        ax1.set_xlabel('Achieved QPS', fontsize=12)
        ax1.set_xlim(0, 130000)
        ax1.set_ylim(0, float(max(2.0, global_max_p95)))
        ax1.set_ylabel('95th Percentile Latency (ms)', color=color1, fontsize=12)
        ax1.plot(mean_qps, mean_p95, marker='o', color=color1, label='95th Percentile Latency', linewidth=2)
        ax1.tick_params(axis='y', labelcolor=color1)
        
        # 0.8ms SLO line
        ax1.axhline(y=0.8, color='r', linestyle='--', label='0.8 ms SLO', linewidth=1.5)
        
        # Plot CPU utilization on right y-axis
        ax2 = ax1.twinx()
        color2 = 'tab:orange'
        ax2.set_ylabel('CPU Utilization (%)', color=color2, fontsize=12)
        ax2.set_ylim(0, 300)  # 0 to 100% for C=1, 200% for C=2, 300% for C=3
        ax2.plot(mean_qps, mean_cpu, marker='s', color=color2, label='CPU Utilization', linewidth=2)
        ax2.tick_params(axis='y', labelcolor=color2)
        
        # Combine legends
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        plt.title(f'Memcached Performance (T={t}, C={c})\nLatency & CPU vs Achieved QPS')
        ax1.grid(True, linestyle=':', alpha=0.6)
        
        plt.tight_layout()
        out_file = f"{OUTPUT_PLOT_PREFIX}{c}.pdf"
        plt.savefig(out_file)
        plt.close()
        print(f"Plot saved to {out_file}")

if __name__ == "__main__":
    main()
