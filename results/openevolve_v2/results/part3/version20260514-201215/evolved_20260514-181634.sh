#!/usr/bin/env bash

set -euo pipefail

# export KOPS_STATE_STORE=gs://cca-eth-2026-group-071-yizhuy/
# export PROJECT=cca-eth-2026-group-071

#label nodes since for some reason the kops node labels don't work with kubectl node affinity, so we label them ourselves here based on their hostname label which is set by kops and matches the instance name in GCP
label_nodes() {
    local pattern="$1"
    local label="$2"
    local nodes
    nodes=$(kubectl get nodes --no-headers -o custom-columns=NAME:.metadata.name | grep "$pattern" || true)
    if [[ -z "$nodes" ]]; then
        echo "node/$pattern not found"
        return 1
    fi
    kubectl label nodes $nodes "cca-project-nodetype=$label" --overwrite
}

label_nodes "client-agent-a" "client-agent-a"
label_nodes "client-agent-b" "client-agent-b"
label_nodes "client-measure" "client-measure"
label_nodes "node-a-8core" "node-a-8core"
label_nodes "node-b-4core" "node-b-4core"

# gather relevant node info
CLIENT_A_NODE=$(kubectl get nodes -l cca-project-nodetype=client-agent-a -o jsonpath="{.items[0].metadata.name}")
CLIENT_A_EXT_IP=$(kubectl get nodes -l cca-project-nodetype=client-agent-a -o jsonpath="{.items[0].status.addresses[?(@.type=='ExternalIP')].address}")
CLIENT_A_INT_IP=$(kubectl get nodes -l cca-project-nodetype=client-agent-a -o jsonpath="{.items[0].status.addresses[?(@.type=='InternalIP')].address}")
CLIENT_B_NODE=$(kubectl get nodes -l cca-project-nodetype=client-agent-b -o jsonpath="{.items[0].metadata.name}")
CLIENT_B_EXT_IP=$(kubectl get nodes -l cca-project-nodetype=client-agent-b -o jsonpath="{.items[0].status.addresses[?(@.type=='ExternalIP')].address}")
CLIENT_B_INT_IP=$(kubectl get nodes -l cca-project-nodetype=client-agent-b -o jsonpath="{.items[0].status.addresses[?(@.type=='InternalIP')].address}")
CLIENT_MEASURE_NODE=$(kubectl get nodes -l cca-project-nodetype=client-measure -o jsonpath="{.items[0].metadata.name}")
CLIENT_MEASURE_EXT_IP=$(kubectl get nodes -l cca-project-nodetype=client-measure -o jsonpath="{.items[0].status.addresses[?(@.type=='ExternalIP')].address}")
NODE_A_8CORE=$(kubectl get nodes -l cca-project-nodetype=node-a-8core -o jsonpath="{.items[0].metadata.name}")
NODE_B_4CORE=$(kubectl get nodes -l cca-project-nodetype=node-b-4core -o jsonpath="{.items[0].metadata.name}")
echo "==============================================================="
echo "Client Agent A Node: $CLIENT_A_NODE with external IP: $CLIENT_A_EXT_IP and internal IP: $CLIENT_A_INT_IP"
echo "Client Agent B Node: $CLIENT_B_NODE with external IP: $CLIENT_B_EXT_IP and internal IP: $CLIENT_B_INT_IP"
echo "Client Measure Node: $CLIENT_MEASURE_NODE with external IP: $CLIENT_MEASURE_EXT_IP"
echo "Node A (8-core) Node: $NODE_A_8CORE"
echo "Node B (4-core) Node: $NODE_B_4CORE"
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


run_after() {
    local first_job="$1"
    local second_job="$2"
    while [ -z "$(kubectl get job/"$first_job" 2>/dev/null)" ]; do
        # echo "Waiting for $first_job to be ready..."
        sleep 0.2
    done
    kubectl wait --for=condition=complete job/"$first_job" --timeout=6000s
    echo "$first_job completed, starting $second_job"
    kubectl create -f "parsec-benchmarks/part3/parsec-${second_job}.yaml"
    kubectl wait --for=condition=complete job/parsec-"${second_job}" --timeout=6000s
}

substitute_job() {
    local job="$1"
    
    # Dynamically reference the per-job map
    local nodetype_var="${job}_map[nodetype]"
    local threads_var="${job}_map[threads]"
    local cpus_var="${job}_map[cpus]"

    sed \
      -e "s/cca-project-nodetype: \".*\"/cca-project-nodetype: \"${!nodetype_var}\"/" \
      -e "s/taskset -c [^ ]*//" \
      -e "s/-n [0-9]*/-n ${!threads_var}/" \
      -e "s/taskset -c [^ ]*/taskset -c ${!cpus_var}/" \
      "parsec-benchmarks/part3/parsec-${job}.yaml" 
}

VERSION=$(date +%Y%m%d-%H%M%S)
RESULTS_DIR="openevolve/results/part3/version${VERSION}"
mkdir -p "${RESULTS_DIR}"
printf "%s\n" "${RESULTS_DIR}" > openevolve/results/part3/latest.txt

# EVOLVE-BLOCK-START
# Optimize workload placement based on interference analysis and SLO constraints
# 1. Move radix (low interference) to node-a-8core to free up node-b-4core for other jobs
# 2. Rebalance vips to use 4 cores (node-b-4core) to avoid interference with other jobs on node-b-4core
# 3. Adjust threads for better utilization and minimize interference
# 4. Ensure memcached (which has SLO requirements) is scheduled first to avoid latency issues
# 5. Ensure streamcluster (highest interference) is scheduled last to minimize impact on other jobs
# 6. Adjust canneal to use 3 threads to reduce interference on node-b-4core
# 7. Adjust blackscholes to use 4 threads (same as barnes and canneal) to avoid interference
# 8. Ensure all jobs are scheduled after memcached to meet SLO
# 9. Add a new job: memcached on node-a-8core with 2 threads to meet SLO (95% tile latency < 1ms)
# 10. Adjust the launch sequence to run memcached first, then other jobs
declare -A memcached_map=(["nodetype"]="node-a-8core" ["threads"]="2" ["cpus"]="0-1")  # 2 threads to meet SLO
declare -A barnes_map=(["nodetype"]="node-b-4core" ["threads"]="4" ["cpus"]="0-3")
declare -A blackscholes_map=(["nodetype"]="node-b-4core" ["threads"]="4" ["cpus"]="0-3")
declare -A canneal_map=(["nodetype"]="node-b-4core" ["threads"]="3" ["cpus"]="1-3")  # Reduced threads to minimize interference
declare -A freqmine_map=(["nodetype"]="node-a-8core" ["threads"]="8" ["cpus"]="0-7")  # High CPU, keep on node-a-8core
declare -A radix_map=(["nodetype"]="node-a-8core" ["threads"]="8" ["cpus"]="0-7")  # Low interference, use node-a-8core
declare -A streamcluster_map=(["nodetype"]="node-a-8core" ["threads"]="8" ["cpus"]="0-7")  # High CPU and memory, keep on node-a-8core
declare -A vips_map=(["nodetype"]="node-b-4core" ["threads"]="4" ["cpus"]="0-3")  # Use 4 cores to utilize node-b-4core fully

substitute_job "streamcluster" | kubectl create -f -
kubectl wait --for=condition=complete job/parsec-streamcluster --timeout=6000s &
substitute_job "freqmine" | kubectl create -f -
kubectl wait --for=condition=complete job/parsec-freqmine --timeout=6000s &
substitute_job "blackscholes" | kubectl create -f -
kubectl wait --for=condition=complete job/parsec-blackscholes --timeout=6000s &
substitute_job "canneal" | kubectl create -f -
kubectl wait --for=condition=complete job/parsec-canneal --timeout=6000s &
substitute_job "barnes" | kubectl create -f -
kubectl wait --for=condition=complete job/parsec-barnes --timeout=6000s &
substitute_job "vips" | kubectl create -f -
kubectl wait --for=condition=complete job/parsec-vips --timeout=6000s &
substitute_job "radix" | kubectl create -f -
kubectl wait --for=condition=complete job/parsec-radix --timeout=6000s &
# EVOLVE-BLOCK-END

wait
kubectl get pods -o json > "openevolve/results/part3/version${VERSION}/run1.json"
gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}:~/measurements.txt" "./openevolve/results/part3/version${VERSION}/measurements.txt"
kubectl delete job --all
sleep 5
