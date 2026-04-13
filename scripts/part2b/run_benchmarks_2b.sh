#!/usr/bin/env bash

set -euo pipefail

mkdir -p results/part2b

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
        for i in {1..5}; do
            echo "==============================================================="
            echo "Running job: $job with $threads threads (Run $i)"
            # Run job
            sed "s/NUMBER_OF_THREADS/$threads/g" "parsec-benchmarks/part2b/${job}.yaml" | kubectl create -f -

            # Wait for completion
            kubectl wait --for=condition=complete job/"$job" --timeout=$TIMEOUT

            # Collect logs immediately (using job/name directly is safer if the job retried and has multiple pods)
            kubectl logs job/"$job" > "results/part2b/${job}_${threads}threads_${i}.txt"

            # Then clean up
            kubectl delete job "$job"
            sleep 5 # Ensure job fully terminates before next loop
        done
    done
done