#!/usr/bin/env bash

set -euo pipefail
#label nodes since for some reason the kops node labels don't work with kubectl node affinity, so we label them ourselves here based on their hostname label which is set by kops and matches the instance name in GCP
kubectl label nodes $(kubectl get nodes --no-headers -o custom-columns=NAME:.metadata.name | grep client-agent-a) cca-project-nodetype=client-agent-a
kubectl label nodes $(kubectl get nodes --no-headers -o custom-columns=NAME:.metadata.name | grep client-agent-b) cca-project-nodetype=client-agent-b
kubectl label nodes $(kubectl get nodes --no-headers -o custom-columns=NAME:.metadata.name | grep client-measure) cca-project-nodetype=client-measure
kubectl label nodes $(kubectl get nodes --no-headers -o custom-columns=NAME:.metadata.name | grep node-a-8core) cca-project-nodetype=node-a-8core
kubectl label nodes $(kubectl get nodes --no-headers -o custom-columns=NAME:.metadata.name | grep node-b-4core) cca-project-nodetype=node-b-4core

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
      "parsec-benchmarks/part3/parsec-${job}.yaml" 
    #   -e "s/taskset -c [^ ]*/taskset -c ${!cpus_var}/" \
}

declare -A barnes_map=(["nodetype"]="node-b-4core" ["threads"]="4" ["cpus"]="0-3")
declare -A blackscholes_map=(["nodetype"]="node-b-4core" ["threads"]="4" ["cpus"]="0-3")
declare -A canneal_map=(["nodetype"]="node-b-4core" ["threads"]="4" ["cpus"]="0-3")
declare -A freqmine_map=(["nodetype"]="node-a-8core" ["threads"]="8" ["cpus"]="0-7")
declare -A radix_map=(["nodetype"]="node-a-8core" ["threads"]="8" ["cpus"]="0-7")
declare -A streamcluster_map=(["nodetype"]="node-a-8core" ["threads"]="8" ["cpus"]="0-7")
declare -A vips_map=(["nodetype"]="node-a-8core" ["threads"]="8" ["cpus"]="0-3")

VERSION=4_memcached4node2
mkdir -p results/part3/version${VERSION}
for i in {1..3}; do
    #static schedule based on info from part 1,2 results, no kubectl affinity or resource requests/limits

    substitute_job "streamcluster" | kubectl create -f -
    substitute_job "freqmine" | kubectl create -f -
    substitute_job "blackscholes" | kubectl create -f -
    substitute_job "canneal" | kubectl create -f -
    substitute_job "barnes" | kubectl create -f -
    substitute_job "vips" | kubectl create -f -
    substitute_job "radix" | kubectl create -f -
    kubectl wait --for=condition=complete job/parsec-streamcluster --timeout=6000s &
    kubectl wait --for=condition=complete job/parsec-freqmine --timeout=6000s &
    kubectl wait --for=condition=complete job/parsec-blackscholes --timeout=6000s &
    kubectl wait --for=condition=complete job/parsec-canneal --timeout=6000s &
    kubectl wait --for=condition=complete job/parsec-barnes --timeout=6000s &
    kubectl wait --for=condition=complete job/parsec-vips --timeout=6000s &
    kubectl wait --for=condition=complete job/parsec-radix --timeout=6000s &
    # run_after "parsec-blackscholes" "vips" &
    # run_after "parsec-vips" "canneal" &



    # substitute_job "freqmine" | kubectl create -f -
    # kubectl wait --for=condition=complete job/parsec-freqmine --timeout=6000s &

    # run_after "parsec-streamcluster" "freqmine" &
    # run_after "parsec-streamcluster" "barnes" &
    # run_after "parsec-barnes" "radix" &

    # run_barnes & # 4 threads, [0-3]
    # kubectl wait --for=condition=complete job/parsec-streamcluster --timeout=6000s &
    # kubectl wait --for=condition=complete job/parsec-radix --timeout=6000s &
    # # run_radix &  # 4 threads, colocated on node-a-8core, after vips
    # # run_blackscholes & # 4 threads, colocated on node-a-8core, after freqmine

    wait
    kubectl get pods -o json > "results/part3/version${VERSION}/run${i}.json"
    gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}:~/measurements.txt" "./results/part3/version${VERSION}/measurements.txt"
    kubectl delete job --all
    sleep 5
done



