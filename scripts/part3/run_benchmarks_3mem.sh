#!/usr/bin/env bash

set -euo pipefail

mkdir -p results/part3_pre

num_threads=(1 2 4 8)
ALL_JOBS=(
  "parsec-barnes"
  "parsec-blackscholes"
  "parsec-canneal"
  "parsec-freqmine"
  "parsec-radix"
  "parsec-streamcluster"
  "parsec-vips"
)
TIMEOUT=6000s

for job in "${ALL_JOBS[@]}"; do
    for threads in "${num_threads[@]}"; do
        echo "==============================================================="
        echo "Running job: $job with $threads threads"
        
        # Substitute NUMBER_OF_THREADS and install 'time' dynamically before running the benchmark
        sed "s/NUMBER_OF_THREADS/$threads/g" "parsec-benchmarks/part2b/${job}.yaml" \
          | sed 's/\.\/run/apt-get update >\/dev\/null \&\& apt-get install -y time >\/dev\/null \&\& \/usr\/bin\/time -v \.\/run/g' \
          | kubectl create -f -

        # Wait for completion
        kubectl wait --for=condition=complete job/"$job" --timeout=$TIMEOUT

        # Collect logs immediately
        kubectl logs job/"$job" > "results/part3_pre/${job}_${threads}threads.txt"

        # Clean up
        kubectl delete job "$job"
        sleep 5
    done
done
