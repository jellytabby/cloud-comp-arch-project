import os
import re
from collections import defaultdict

JOBS = [
    "parsec-barnes",
    "parsec-blackscholes",
    "parsec-canneal",
    "parsec-freqmine",
    "parsec-radix",
    "parsec-streamcluster",
    "parsec-vips"
]

INTERFERENCES = [
    "ibench-cpu",
    "ibench-l1d",
    "ibench-l1i",
    "ibench-l2",
    "ibench-llc",
    "ibench-membw"
]

RESULTS_DIR = 'results/part2a'

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

def get_color(ratio):
    if ratio <= 1.3:
        return r"\cellcolor{Green}"
    elif ratio <= 2.0:
        return r"\cellcolor{YellowOrange}"
    else:
        return r"\cellcolor{Red}"

def main():
    results = defaultdict(dict)
    
    for job in JOBS:
        # Gather baseline (no_interference) times
        base_times = []
        for i in range(1, 4):
            path = os.path.join(RESULTS_DIR, f"no_interference_{job}_{i}.txt")
            t = parse_time(path)
            if t is not None:
                base_times.append(t)
        
        baseline_avg = sum(base_times) / len(base_times) if base_times else None
        results[job]['none'] = baseline_avg
        
        # Gather interference times
        for interference in INTERFERENCES:
            times = []
            for i in range(1, 4):
                path = os.path.join(RESULTS_DIR, f"{interference}_{job}_{i}.txt")
                t = parse_time(path)
                if t is not None:
                    times.append(t)
            
            avg = sum(times) / len(times) if times else None
            results[job][interference] = avg

    # Print LaTeX table
    print(r"        \begin{center}")
    print(r"        \begin{tabular}{ |c|c|c|c|c|c|c|c| }")
    print(r"        \hline")
    print(r"         \textbf{Workload} & \texttt{\textbf{none}} & \texttt{\textbf{cpu}} & \texttt{\textbf{l1d}} & \texttt{\textbf{l1i}} & \texttt{\textbf{l2}} & \texttt{\textbf{llc}} & \texttt{\textbf{memBW}}  \\")
    print(r"         \hline\hline")

    for job in JOBS:
        job_name = job.replace("parsec-", "")
        base_time = results[job]['none']
        
        row = [f"        {job_name}"]
        
        if base_time is None or base_time == 0:
            row.append("1.00")
            for _ in INTERFERENCES:
                row.append("N/A")
        else:
            row.append("1.00")
            
            for interference in INTERFERENCES:
                t = results[job][interference]
                if t is None:
                    row.append("")
                else:
                    ratio = t / base_time
                    color = get_color(ratio)
                    row.append(f"{color} {ratio:.2f}")
        
        print(" & ".join(row) + r" \\  \hline")

    print(r"        \end{tabular}")
    print(r"        \end{center}")

if __name__ == "__main__":
    main()
