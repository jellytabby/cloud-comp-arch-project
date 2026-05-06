import os
import glob
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

RESULTS_DIR = "results/part4/1a_first"
OUTPUT_PLOT = "plots/part4/latency_vs_qps_4.1a.pdf"

os.makedirs(os.path.dirname(OUTPUT_PLOT), exist_ok=True)

def load_data(t, c):
    """
    Returns a dict mapping target_qps -> list of (achieved_qps, p95_latency) across reps
    """
    data = {}
    for rep in range(1, 4):
        filepath = os.path.join(RESULTS_DIR, f"measurements_T{t}_C{c}_rep{rep}.txt")
        if not os.path.exists(filepath):
            print(f"Warning: {filepath} not found.")
            continue
            
        with open(filepath, "r") as f:
            for line in f:
                if line.startswith("read"):
                    parts = line.strip().split()
                    # indices based on the measurement file format:
                    # 12 is p95 (in us, we divide by 1000 for ms)
                    # 16 is achieved QPS
                    # 17 is target QPS
                    try:
                        p95 = float(parts[12]) / 1000.0  # ms
                        qps = float(parts[16])
                        target = int(parts[17])
                    except (IndexError, ValueError):
                        continue
                    
                    if target not in data:
                        data[target] = []
                    data[target].append((qps, p95))
    return data

def main():
    plt.figure(figsize=(10, 6))
    
    markers = ['o', 's', '^', 'v', 'D', '<', '>', 'p', '*']
    colors = plt.cm.get_cmap('tab10', 9).colors
    idx = 0

    for t in [1, 2, 3]:
        for c in [1, 2, 3]:
            data = load_data(t, c)
            if not data:
                continue
                
            targets = sorted(data.keys())
            mean_qps = []
            mean_p95 = []
            std_p95 = []
            
            for tgt in targets:
                qps_vals = [d[0] for d in data[tgt]]
                p95_vals = [d[1] for d in data[tgt]]
                
                mean_qps.append(np.mean(qps_vals))
                mean_p95.append(np.mean(p95_vals))
                std_p95.append(np.std(p95_vals))
                
            label = f"T={t}, C={c}"
            plt.errorbar(mean_qps, mean_p95, yerr=std_p95, label=label, marker=markers[idx], capsize=3, alpha=0.8)
            idx += 1

    plt.axhline(y=0.8, color='r', linestyle='--', label='0.8 ms SLO')
    plt.xlabel('Achieved QPS')
    plt.ylabel('95th Percentile Latency (ms)')
    plt.title('Memcached Performance: 95th Percentile Latency vs. Achieved QPS\n(Averaged over 3 runs)')
    plt.legend()
    plt.grid(True, linestyle=':', alpha=0.6)
    
    plt.tight_layout()
    plt.savefig(OUTPUT_PLOT)
    print(f"Plot saved to {OUTPUT_PLOT}")

if __name__ == "__main__":
    main()
