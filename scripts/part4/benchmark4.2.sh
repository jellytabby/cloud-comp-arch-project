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

python_modules=(
    "psutil"
    "docker"
)

memcached_runtime_seconds=1200

VERSION=11
OUTPUT_DIR="./results/part4/4/version_${VERSION}"
mkdir -p "$OUTPUT_DIR"

gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "./scripts/part4/scheduler_logger.py" "${MEMCACHED_SERVER_NODE}:~/scheduler_logger.py"

CLIENT_CMD="cd memcache-perf-dynamic && ./mcperf -T 8 -A"
MEASURE_CMD="cd memcache-perf-dynamic && ./mcperf -s ${MEMCACHED_SERVER_INT_IP} -a ${CLIENT_INT_IP} --noload -T 8 -C 8 -D 4 -Q 1000 -c 8 -t ${memcached_runtime_seconds} --qps_interval 5 --qps_min 5000 --qps_max 110000 --qps_seed 2345 "


#start memcached because restarting it kills the measure
memcached_threads=4
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}" --command "sudo sed -i 's/^-t [0-9]*/-t ${memcached_threads}/' /etc/memcached.conf && sudo systemctl restart memcached && sudo systemctl status memcached"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_NODE}" --command "TERM=xterm-256color tmux new-session -d \"bash -c '${CLIENT_CMD}'\""
# start client agent in tmux session
echo "started client agent on ${CLIENT_NODE} with command: ${CLIENT_CMD}"
# load data on measure node and then run measurements
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}" --command "cd memcache-perf-dynamic && ./mcperf -s ${MEMCACHED_SERVER_INT_IP} --loadonly"
echo "loaded data on measure node with command: cd memcache-perf-dynamic && ./mcperf -s ${MEMCACHED_SERVER_INT_IP} --loadonly"
# gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}" --command "sudo usermod -a -G docker \$USER"


for module in "${python_modules[@]}"; do
    gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}" --command "pip3 install ${module} --user --break-system-packages"
done


for i in {4..5}; do
    gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}" --command "TERM=xterm-256color tmux new-session -d 'bash -c \"${MEASURE_CMD} |& tee ~/measurements_${i}.txt\"'"
    sleep 5
    sleep ${memcached_runtime_seconds} & # wait for memcached runtime to be over before collecting results, ensures we have the full runtime of memcached in our measurements and logs
    gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}" --command "echo 'mpstat -A 1 | while read line; do echo \$(date +%s%3N) \$line; done | tee ~/mpstat_run${i}.txt' > ~/run_mpstat.sh && TERM=xterm-256color tmux new-session -d bash ~/run_mpstat.sh"
    # start scheduler logger
    gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}" --command "python3 ~/scheduler_logger.py |& tee ~/scheduler_log_${i}.txt"

    wait # wait for memcached runtime to be over before collecting results, ensures we have the full runtime of memcached in our measurements and logs

    gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}" --command "pids=\$(docker ps -aq); if [ -n \"\$pids\" ]; then docker inspect \$pids > ~/container_inspect_${i}.txt; else echo 'no containers' > ~/container_inspect_${i}.txt; fi"
    gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}:~/container_inspect_${i}.txt" "${OUTPUT_DIR}/container_inspect_${i}.txt"
    gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}" --command "pids=\$(docker ps -aq); if [ -n \"\$pids\" ]; then docker rm -f \$pids; fi"
    gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}:~/mpstat_run${i}.txt" "${OUTPUT_DIR}/mpstat_run${i}.txt"
    gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}" --command "killall mpstat"
    gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${CLIENT_MEASURE_NODE}:~/measurements_${i}.txt" "${OUTPUT_DIR}/measurements_rep${i}.txt"
    gcloud compute scp --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "${MEMCACHED_SERVER_NODE}:~/scheduler_log_${i}.txt" "${OUTPUT_DIR}/scheduler_log_rep${i}.txt"
done
