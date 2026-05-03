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




# setup memcached pod
echo "==============================================================="
echo "Setting up memcached pod with 1 thread and cpuset to core 0"
if kubectl get pod memcached &> /dev/null; then
    echo "Memcached pod already exists, deleting it first..."
    kubectl delete pod memcached
    kubectl delete service memcached-11211
    while kubectl get pod memcached &> /dev/null && kubectl get service memcached-11211 &> /dev/null; do
        echo "Waiting for memcached pod and service to be deleted..."
        sleep 5
    done
fi
kubectl create -f "parsec-benchmarks/part3/part3_memcache-t1-cpuset.yaml"
kubectl wait --for=condition=ready pod/memcached --timeout=600s
kubectl expose pod memcached --name memcached-11211 --type LoadBalancer --port 11211 --protocol TCP
MEMCACHED_IP=""
while [ -z "$MEMCACHED_IP" ]; do
    echo "Waiting for memcached LoadBalancer IP..."
    MEMCACHED_IP=$(kubectl get service memcached-11211 -o jsonpath="{.status.loadBalancer.ingress[0].ip}")
    sleep 5
done
# MEMCACHED_IP=$(kubectl get service memcached-11211 -o jsonpath="{.status.loadBalancer.ingress[0].ip}")
MEMCACHED_IP=$(kubectl get pod memcached -o jsonpath="{.status.podIP}")
echo "Memcached is available at IP: $MEMCACHED_IP"
echo "==============================================================="

# #setup client agents and measure
CLIENT_A_CMD="cd memcache-perf-dynamic && ./mcperf -T 2 -A"
CLIENT_B_CMD="cd memcache-perf-dynamic && ./mcperf -T 4 -A"
CLIENT_MEASURE_CMD_LOAD="cd memcache-perf-dynamic && ./mcperf -s ${MEMCACHED_IP} --loadonly"
CLIENT_MEASURE_CMD_RUN="cd memcache-perf-dynamic && ./mcperf -s ${MEMCACHED_IP} -a ${CLIENT_A_INT_IP} -a ${CLIENT_B_INT_IP} --noload -T 6 -C 4 -D 4 -Q 1000 -c 4 -t 10 --scan 30000:30500:5 |& tee ~/measurements.txt"
# echo "$CLIENT_MEASURE_CMD"

# for some reason needs the gcloud ssh before normal ssh works, so we use gcloud here
gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "./scripts/part3/build_mcperf.sh" "${CLIENT_A_NODE}:~/build_mcperf.sh"
# gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_A_NODE}" --command "chmod +x ~/build_mcperf.sh && ~/build_mcperf.sh"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_A_NODE}" --command "TERM=xterm-256color tmux new-session -d \"bash -c '${CLIENT_A_CMD}'\""

echo "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b ${CLIENT_A_NODE}"
# read -p "Press Enter after verifying that client agent A is running its benchmark..." 

# # echo "sshed into client agent A"

gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "./scripts/part3/build_mcperf.sh" "${CLIENT_B_NODE}:~/build_mcperf.sh"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_B_NODE}" --command "chmod +x ~/build_mcperf.sh && ~/build_mcperf.sh"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_B_NODE}" --command "TERM=xterm-256color tmux new-session -d \"bash -c '${CLIENT_B_CMD}'\""

echo "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b ${CLIENT_B_NODE}"
# read -p "Press Enter after verifying that client agent B is running its benchmark..."

# echo "sshed into client agent B"

gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "./scripts/part3/build_mcperf.sh" "${CLIENT_MEASURE_NODE}:~/build_mcperf.sh"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}" --command "chmod +x ~/build_mcperf.sh && ~/build_mcperf.sh"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}" --command "${CLIENT_MEASURE_CMD_LOAD}"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}" --command "TERM=xterm-256color tmux new-session -d \"bash -c '${CLIENT_MEASURE_CMD_RUN}'\""
echo  "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b ${CLIENT_MEASURE_NODE} --command \"TERM=xterm-256color tmux new-session -d \"bash -c '${CLIENT_MEASURE_CMD_RUN}'\""

echo "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b ${CLIENT_MEASURE_NODE}" 
# read -p "Press Enter after verifying that client measure node is running its benchmark..."

echo "sshed into client measure node and started measurement client"
sleep 10
echo "==============================================================="
echo "Client agents and measurement client are set up and running benchmarks against memcached"
echo "$(gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}" --command "cat measurements.txt")"
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

run_vips() {
    kubectl wait --for=condition=complete job/parsec-blackscholes --timeout=6000s
    echo "blackscholes completed, starting vips"
    kubectl create -f "parsec-benchmarks/part3/parsec-vips.yaml" # 4 threads, colocated on node-a-8core
    kubectl wait --for=condition=complete job/parsec-vips --timeout=6000s
}

run_barnes() {
    kubectl wait --for=condition=complete job/parsec-blackscholes --timeout=6000s
    sleep 1 # so that we dont crash on missing job
    kubectl wait --for=condition=complete job/parsec-vips --timeout=6000s
    echo "vips completed, starting barnes"
    kubectl create -f "parsec-benchmarks/part3/parsec-barnes.yaml" # 4 threads, colocated on node-a-8core
    kubectl wait --for=condition=complete job/parsec-barnes --timeout=6000s
}

run_radix() {
    # kubectl wait --for=condition=complete job/parsec-blackscholes --timeout=6000s
    # kubectl wait --for=condition=complete job/parsec-streamcluster --timeout=6000s
    
    kubectl wait --for=condition=complete job/parsec-canneal --timeout=6000s
    sleep 2 # so that we dont crash on missing job
    kubectl wait --for=condition=complete job/parsec-vips --timeout=6000s
    # echo "blackscholes and streamcluster completed, starting radix"
    kubectl create -f "parsec-benchmarks/part3/parsec-radix.yaml" # 1 thread
    kubectl wait --for=condition=complete job/parsec-radix --timeout=6000s
}

run_blackscholes() {
    kubectl wait --for=condition=complete job/parsec-barnes --timeout=6000s
    echo "barnes completed, starting blackscholes"
    kubectl create -f "parsec-benchmarks/part3/parsec-blackscholes.yaml" # 4 threads
    kubectl wait --for=condition=complete job/parsec-blackscholes --timeout=6000s
}

run_canneal() {
    kubectl wait --for=condition=complete job/parsec-freqmine --timeout=6000s
    echo "freqmine completed, starting canneal"
    kubectl create -f "parsec-benchmarks/part3/parsec-canneal.yaml" # 4 threads
    kubectl wait --for=condition=complete job/parsec-canneal --timeout=6000s
}



VERSION=3
mkdir -p results/part3/version${VERSION}
sleep 10 # just to be safe that everything is up and running before we start the benchmarks, especially the measurement client
for i in {1..3}; do
    #static schedule based on info from part 1,2 results, no kubectl affinity or resource requests/limits

    # colocated with memcached on node-b-4core
    kubectl create -f "parsec-benchmarks/part3/parsec-streamcluster.yaml" # 4 threads 
    # kubectl create -f "parsec-benchmarks/part3/parsec-blackscholes.yaml" # one thread
    echo "created streamcluster"
    # kubectl wait --for=condition=complete job/parsec-blackscholes --timeout=6000s &

    # colocated on node-a-8core
    # kubectl create -f "parsec-benchmarks/part3/parsec-canneal.yaml" # 4 threads
    kubectl create -f "parsec-benchmarks/part3/parsec-freqmine.yaml" # 4 threads [4-7]
    kubectl create -f "parsec-benchmarks/part3/parsec-blackscholes.yaml" # 3 threads [0-2]
    kubectl create -f "parsec-benchmarks/part3/parsec-radix.yaml" # 1 thread [3]
    echo "created freqmine, blackscholes and radix"

    run_canneal & # 4 threads, [4-7]
    run_vips & # 4 threads, [0-3]
    run_barnes & # 4 threads, [0-3]
    kubectl wait --for=condition=complete job/parsec-streamcluster --timeout=6000s &
    kubectl wait --for=condition=complete job/parsec-radix --timeout=6000s &
    # run_radix &  # 4 threads, colocated on node-a-8core, after vips
    # run_blackscholes & # 4 threads, colocated on node-a-8core, after freqmine

    wait
    kubectl get pods -o json > "results/part3/version${VERSION}/run${i}.json"
    gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}:~/measurements.txt" "./results/part3/version${VERSION}/measurements.txt"
    echo "All jobs completed for version ${VERSION} run ${i}, collecting logs and cleaning up"

    for job in "${ALL_JOBS[@]}"; do
            kubectl logs job/"$job" > "results/part3/version${VERSION}/${job}_${i}.txt"
    done
    kubectl delete jobs --all --ignore-not-found
    sleep 5
done



