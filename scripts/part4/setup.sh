#!/usr/bin/env bash

set -euo pipefail
#label nodes since for some reason the kops node labels don't work with kubectl node affinity, so we label them ourselves here based on their hostname label which is set by kops and matches the instance name in GCP
kubectl label nodes $(kubectl get nodes --no-headers -o custom-columns=NAME:.metadata.name | grep client-agent) cca-project-nodetype=client-agent
kubectl label nodes $(kubectl get nodes --no-headers -o custom-columns=NAME:.metadata.name | grep client-measure) cca-project-nodetype=client-measure
kubectl label nodes $(kubectl get nodes --no-headers -o custom-columns=NAME:.metadata.name | grep memcache-server) cca-project-nodetype=memcache-server

# gather relevant node info
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

echo "===========================memcached==============================="
echo "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b ${MEMCACHED_SERVER_NODE}"
echo "==============================================================="
gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "./scripts/part4/install_memcached.sh" "${MEMCACHED_SERVER_NODE}:~/install_memcached.sh"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}" --command "chmod +x ~/install_memcached.sh && ~/install_memcached.sh ${MEMCACHED_SERVER_INT_IP}"
gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "./scripts/part4/install_docker.sh" "${MEMCACHED_SERVER_NODE}:~/install_docker.sh"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}" --command "chmod +x ~/install_docker.sh && sudo ~/install_docker.sh"
echo "=============================memcached==============================="
echo "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b ${MEMCACHED_SERVER_NODE}"
echo "==============================================================="


# #setup client agents and measure
# CLIENT_CMD="cd memcache-perf-dynamic && ./mcperf -T 8 -A"
# CLIENT_MEASURE_CMD_LOAD="cd memcache-perf-dynamic && ./mcperf -s ${MEMCACHED_SERVER_INT_IP} --loadonly"
# CLIENT_MEASURE_CMD_RUN="cd memcache-perf-dynamic && ./mcperf -s ${MEMCACHED_SERVER_INT_IP} -a ${CLIENT_INT_IP} --noload -T 6 -C 4 -D 4 -Q 1000 -c 4 -t 10 --scan 30000:30500:5 |& tee ~/measurements.txt"
# echo "$CLIENT_MEASURE_CMD"

echo "===========================client================================="
echo "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b ${CLIENT_NODE}"
echo "TERM=xterm-256color tmux attach"
echo "===================================================================="
# for some reason needs the gcloud ssh before normal ssh works, so we use gcloud here
gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "./scripts/part4/build_mcperf.sh" "${CLIENT_NODE}:~/build_mcperf.sh"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_NODE}" --command "chmod +x ~/build_mcperf.sh && ~/build_mcperf.sh"
# gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_NODE}" --command "TERM=xterm-256color tmux new-session -d \"bash -c '${CLIENT_CMD}'\""
echo "===========================client================================="
echo "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b ${CLIENT_NODE}"
echo "TERM=xterm-256color tmux attach"
echo "===================================================================="

# echo "sshed into client agent B"

echo "===========================client measure================================="
echo "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b ${CLIENT_MEASURE_NODE}" 
# echo "TERM=xterm-256color tmux attach"
echo "=========================================================================="
gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "./scripts/part4/build_mcperf.sh" "${CLIENT_MEASURE_NODE}:~/build_mcperf.sh"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}" --command "chmod +x ~/build_mcperf.sh && ~/build_mcperf.sh"
# gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}" --command "${CLIENT_MEASURE_CMD_LOAD}"
# gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}" --command "TERM=xterm-256color tmux new-session -d \"bash -c '${CLIENT_MEASURE_CMD_RUN}'\""
# echo  "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b ${CLIENT_MEASURE_NODE} --command \"TERM=xterm-256color tmux new-session -d \"bash -c '${CLIENT_MEASURE_CMD_RUN}'\""
echo "===========================client measure================================="
echo "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b ${CLIENT_MEASURE_NODE}" 
# echo "TERM=xterm-256color tmux attach"
echo "=========================================================================="
