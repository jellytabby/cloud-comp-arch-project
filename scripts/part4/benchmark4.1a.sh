#!/usr/bin/env bash

set -euo pipefail

CLIENT_NODE=$(kubectl get nodes -l cca-project-nodetype=client-agent -o jsonpath="{.items[0].metadata.name}")
CLIENT_EXT_IP=$(kubectl get nodes -l cca-project-nodetype=client-agent -o jsonpath="{.items[0].status.addresses[?(@.type=='ExternalIP')].address}")
CLIENT_INT_IP=$(kubectl get nodes -l cca-project-nodetype=client-agent -o jsonpath="{.items[0].status.addresses[?(@.type=='InternalIP')].address}")
CLIENT_MEASURE_NODE=$(kubectl get nodes -l cca-project-nodetype=client-measure -o jsonpath="{.items[0].metadata.name}")
CLIENT_MEASURE_EXT_IP=$(kubectl get nodes -l cca-project-nodetype=client-measure -o jsonpath="{.items[0].status.addresses[?(@.type=='ExternalIP')].address}")
MEMCACHED_SERVER_NODE=$(kubectl get nodes -l cca-project-nodetype=memcache-server -o jsonpath="{.items[0].metadata.name}")
MEMCACHED_SERVER_INT_IP=$(kubectl get nodes -l cca-project-nodetype=memcache-server -o jsonpath="{.items[0].status.addresses[?(@.type=='InternalIP')].address}")

echo "==============================================================="
echo "Client Agent A Node: $CLIENT_NODE with external IP: $CLIENT_EXT_IP and internal IP: $CLIENT_INT_IP"
echo "Client Measure Node: $CLIENT_MEASURE_NODE with external IP: $CLIENT_MEASURE_EXT_IP"
echo "Memcached Server Node: $MEMCACHED_SERVER_NODE with internal IP: $MEMCACHED_SERVER_INT_IP"
echo "==============================================================="



OUTPUT_DIR="./results/part4/1a"
mkdir -p "$OUTPUT_DIR"


CLIENT_CMD="cd memcache-perf-dynamic && ./mcperf -T 8 -A"
MEASURE_CMD="cd memcache-perf-dynamic && ./mcperf -s ${MEMCACHED_SERVER_INT_IP} -a ${CLIENT_INT_IP} --noload -T 8 -C 8 -D 4 -Q 1000 -c 8 -t 2 --scan 5000:125000:10000"

gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_NODE}" --command "TERM=xterm-256color tmux new-session -d \"bash -c '${CLIENT_CMD}'\""
echo "started client agent on ${CLIENT_NODE} with command: ${CLIENT_CMD}"

gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}" --command "cd memcache-perf-dynamic && ./mcperf -s ${MEMCACHED_SERVER_INT_IP} --loadonly"
for T in 1 2 3; do
    for C in 1 2 3; do
        gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}" --command "sudo sed -i 's/^-t [0-9]*/-t ${T}/' /etc/memcached.conf && sudo systemctl restart memcached && sudo systemctl status memcached"
        gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}" --command "sudo taskset -a -cp 0-$((C-1)) \$(pgrep memcached)"
        sleep 5 # give some time for memcached to restart and apply the new settings
        for reps in {1..3}; do
            echo "Running with T=$T, C=$C, repetition $reps"
            ADJUSTED_CMD="${MEASURE_CMD} |& tee ~/measurements_T${T}_C${C}_rep${reps}.txt"
            gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}" --command "${ADJUSTED_CMD}"
            gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}:~/measurements_T${T}_C${C}_rep${reps}.txt" "${OUTPUT_DIR}/measurements_T${T}_C${C}_rep${reps}.txt"
        done
    done
done