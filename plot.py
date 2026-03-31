import os
import glob
import numpy as np
import matplotlib.pyplot as plt

def main():
    # Standard 7 configurations as described in the task description
    configs = ["no_interference", "cpu", "l1d", "l1i", "l2", "llc", "membw"]
    
    # Store aggregated data: config -> target_qps -> { 'qps': [], 'p95': [] }
    data = {}
    
    # Track the number of runs per configuration
    runs_per_config = {}
    
    for config in configs:
        # Match files like results/cpu0.txt, results/cpu1.txt, etc.
        files = glob.glob(f"results/{config}[0-9]*.txt")
        if not files:
            print(f"Warning: No data found for '{config}'. Skipping...")
            continue
            
        data[config] = {}
        runs = len(files)
        runs_per_config[config] = runs
        
        for file in files:
            with open(file, 'r') as f:
                for line in f:
                    if line.startswith('read'):
                        parts = line.strip().split()
                        try:
                            # Parse QPS, target, and p95 latency
                            target = float(parts[-1])
                            qps = float(parts[-2])
                            
                            # Convert p95 from microseconds to milliseconds
                            p95 = float(parts[-6]) / 1000.0 
                            
                            if target not in data[config]:
                                data[config][target] = {'qps': [], 'p95': []}
                                
                            data[config][target]['qps'].append(qps)
                            data[config][target]['p95'].append(p95)
                        except (ValueError, IndexError):
                            pass
                            
    # Initialize the plot
    plt.figure(figsize=(10, 6))
    
    # Minimum valid runs to declare what we averaged across (as required by prompt)
    max_runs = max([r for r in runs_per_config.values()] + [0])
    print(f"Generating plot averaging across up to {max_runs} runs per configuration.")
    
    for config, targets in data.items():
        sorted_targets = sorted(targets.keys())
        qps_means = []
        qps_errs = []
        p95_means = []
        p95_errs = []
        
        runs = runs_per_config[config]
        
        for target in sorted_targets:
            q_vals = targets[target]['qps']
            p_vals = targets[target]['p95']
            
            qps_means.append(np.mean(q_vals))
            qps_errs.append(np.std(q_vals, ddof=1) if len(q_vals) > 1 else 0)
            
            p95_means.append(np.mean(p_vals))
            p95_errs.append(np.std(p_vals, ddof=1) if len(p_vals) > 1 else 0)
            
        label = f"{config} ({runs} runs)"
        
        plt.errorbar(
            qps_means, p95_means, 
            xerr=qps_errs, yerr=p95_errs, 
            fmt='-o', markersize=4, capsize=3,
            label=label
        )
        
    # Formatting as per task description
    plt.xlim(0, 80000)
    plt.ylim(0, 6)
    
    # X-axis label with QPS
    plt.xlabel('Achieved Queries per second (QPS)')
    
    # Y-axis label with 95th percentile latency in ms
    plt.ylabel('95th percentile latency (ms)')
    
    plt.title(f'Performance with and without interference\n(Averaged across {max_runs} runs)')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    
    # Save and show
    output_filename = 'latency_vs_qps'
    plt.savefig(f"{output_filename}.png", dpi=600)
    plt.savefig(f"{output_filename}.pdf", dpi=600)
    print(f"Plot saved successfully to {output_filename}")

if __name__ == "__main__":
    main()