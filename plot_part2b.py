import os
import re
import matplotlib.pyplot as plt

JOBS = [
    "parsec-barnes",
    "parsec-blackscholes",
    "parsec-canneal",
    "parsec-freqmine",
    "parsec-radix",
    "parsec-streamcluster",
    "parsec-vips"
]

THREADS = [1, 2, 4, 8]
NUM_RUNS = 5
RESULTS_DIR = 'results/part2b'

def parse_time(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r') as f:
        content = f.read()
        
        # Look for standard bash time format: real    2m32.282s
        m = re.search(r'real\s+(?:(\d+)m)?([\d\.]+)s', content)
        if m:
            mins = float(m.group(1)) if m.group(1) else 0.0
            secs = float(m.group(2))
            return mins * 60 + secs
        
        # Look for alternative time format: real    1.23
        m2 = re.search(r'real\s+([\d\.]+)', content)
        if m2:
            return float(m2.group(1))
    return None

def main():
    plt.figure(figsize=(10, 6))
    
    for job in JOBS:
        speedups = []
        base_time = None
        
        for threads in THREADS:
            times = []
            for i in range(1, NUM_RUNS + 1):
                path = os.path.join(RESULTS_DIR, f"{job}_{threads}threads_{i}.txt")
                t = parse_time(path)
                if t is not None:
                    times.append(t)
            
            if not times:
                print(f"Warning: No valid data found for {job} with {threads} threads.")
                speedups.append(None)
                continue
                
            avg_time = sum(times) / len(times)
            
            if threads == 1:
                base_time = avg_time
                speedups.append(1.0) # Speedup for 1 thread is always 1
            else:
                if base_time is not None:
                    speedups.append(base_time / avg_time)
                else:
                    speedups.append(None)
                    
        # Plot only valid data points
        valid_threads = [t for t, s in zip(THREADS, speedups) if s is not None]
        valid_speedups = [s for s in speedups if s is not None]
        
        if valid_threads:
            plt.plot(valid_threads, valid_speedups, marker='o', label=job.replace("parsec-", ""))
            
    # Add theoretical linear speedup
    plt.plot(THREADS, THREADS, 'k--', linewidth=1, alpha=0.7, label='Ideal (Linear) Speedup')
            
    # Configure graph appearance
    plt.title('Speedup vs Number of Threads')
    plt.xlabel('Number of Threads')
    plt.ylabel(r'Speedup ($\mathrm{Time}_1 / \mathrm{Time}_n$)')
    plt.xticks(THREADS)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.legend(loc='upper left')
    plt.tight_layout()
    
    # Save the plot
    output_path = 'plots/part2b/speedup_vs_threads.png'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=300)
    plt.savefig(output_path.replace('.png', '.pdf'))
    print(f"Plots saved to {output_path} and .pdf")
    
if __name__ == "__main__":
    main()
