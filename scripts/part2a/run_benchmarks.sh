#!/usr/bin/env bash

set -euo pipefail

mkdir -p results/part2a

# get name of parsec node
PARSEC_NODE=$(kubectl get nodes -l cca-project-nodetype=parsec -o jsonpath="{.items[0].metadata.name}")
# kops already applied the cca-project-nodetype=parsec label from part2a.yaml
echo "==============================================================="
echo "Parsec node is: $PARSEC_NODE"
echo "==============================================================="

ALL_JOBS=(
  "parsec-barnes"
  "parsec-blackscholes"
  "parsec-canneal"
  "parsec-freqmine"
  "parsec-radix"
  "parsec-streamcluster"
  "parsec-vips"
)

ALL_INTERFERENCES=(
  "ibench-cpu"
  "ibench-l1d"
  "ibench-l1i"
  "ibench-l2"
  "ibench-llc"
  "ibench-membw"
)

TIMEOUT=6000s

# for job in "${ALL_JOBS[@]}"; do
#     for i in {1..3}; do
#       echo "==============================================================="
#       echo "Running job: $job"
#       # Run job
#       kubectl create -f "parsec-benchmarks/part2a/$job.yaml"

#       # Wait for completion
#       kubectl wait --for=condition=complete job/"$job" --timeout=$TIMEOUT

#       # Collect logs immediately (using job/name directly is safer if the job retried and has multiple pods)
#       kubectl logs job/"$job" > "results/part2a/no_interference_${job}_$i.txt"

#       # Then clean up
#       kubectl delete job "$job"
#       sleep 5 # Ensure job fully terminates before next loop
#     done
# done

for interference in "${ALL_INTERFERENCES[@]}"; do
  echo "==============================================================="
  echo "Running interference: $interference"
  echo "==============================================================="
  # Run interference
  kubectl create -f "interference/${interference}.yaml"
  
  # Wait for completion
  kubectl wait --for=condition=Ready pod/"$interference" --timeout=$TIMEOUT
  sleep 30 # Give it a bit of time to stabilize and start causing interference

    for job in "${ALL_JOBS[@]}"; do
        for i in {1..3}; do
            echo "==============================================================="
            echo "Running job: $job"
            # Run job
            kubectl create -f "parsec-benchmarks/part2a/$job.yaml"

            # Wait for completion
            kubectl wait --for=condition=complete job/"$job" --timeout=$TIMEOUT

            # Collect logs immediately (using job/name directly is safer)
            kubectl logs job/"$job" > "results/part2a/${interference}_${job}_$i.txt"

            # Then clean up
            kubectl delete job "$job"
            sleep 5 # Ensure job fully terminates before next loop
        done
    done
echo "==============================================================="
# kubectl delete blocks until the pod is fully terminated by default
kubectl delete pod "$interference"
sleep 10
done
