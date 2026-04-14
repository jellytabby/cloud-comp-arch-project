import os
import re

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
# Make the path absolute relative to the script's location
script_dir = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(script_dir, '../../results/part3_pre')

def parse_memory(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r') as f:
        content = f.read()
        # Search for the output from /usr/bin/time -v
        m = re.search(r'Maximum resident set size \(kbytes\):\s+(\d+)', content)
        if m:
            # Convert kilobytes to gigabytes for readability
            return float(m.group(1)) / (1024.0 * 1024.0)
    return None

def main():
    print(r"\begin{table}[h]")
    print(r"\centering")
    print(r"\renewcommand{\arraystretch}{1.2}")
    print(r"\begin{tabular}{|l|c|c|c|c|}")
    print(r"\hline")
    print(r"\textbf{Benchmark} & \textbf{1 Thread (GB)} & \textbf{2 Threads (GB)} & \textbf{4 Threads (GB)} & \textbf{8 Threads (GB)} \\")
    print(r"\hline\hline")

    for job in JOBS:
        row_data = [job.replace("parsec-", "")]
        for t in THREADS:
            filepath = os.path.join(RESULTS_DIR, f"{job}_{t}threads.txt")
            mem_mb = parse_memory(filepath)
            
            if mem_mb is not None:
                row_data.append(f"{mem_mb:.2f}")
            else:
                row_data.append("N/A")
                
        print(" & ".join(row_data) + r" \\ \hline")

    print(r"\end{tabular}")
    print(r"\caption{Peak memory footprint (Maximum Resident Set Size) derived from \texttt{/usr/bin/time -v} across different thread counts.}")
    print(r"\label{tab:memory_footprint}")
    print(r"\end{table}")

if __name__ == '__main__':
    main()
