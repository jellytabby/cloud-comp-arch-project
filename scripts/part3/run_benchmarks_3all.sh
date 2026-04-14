#!/usr/bin/env bash

set -euo pipefail

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
kubectl create -f "parsec-benchmarks/part3/part3_memcache-t1-cpuset.yaml"
kubectl wait --for=condition=ready pod/memcached --timeout=300s
kubectl expose pod memcached --name memcached-11211 --type LoadBalancer --port 11211 --protocol TCP
kubectl wait --for=condition=available --timeout=300s service/memcached-11211
MEMCACHED_IP=$(kubectl get service memcached-11211 -o jsonpath="{.status.loadBalancer.ingress[0].ip}")
echo "Memcached is available at IP: $MEMCACHED_IP"
echo "==============================================================="

#setup client agents and measure
CLIENT_A_CMD="./mcperf -T 2 -A"
CLIENT_B_CMD="./mcperf -T 4 -A"
CLIENT_MEASURE_CMD="./mcperf -s ${MEMCACHED_IP} --loadonly && ./mcperf -s ${MEMCACHED_IP} -a ${CLIENT_A_INT_IP} -a ${CLIENT_B_INT_IP} --noload -T 6 -C 4 -D 4 -Q 1000 -c 4 -t 10 --scan 30000:30500:5 > ~/measurements.txt"

# for some reason needs the gcloud ssh before normal ssh works, so we use gcloud here
rsync -avz -e "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b --" "./scripts/part3/build_mcperf.sh" "ubuntu@${CLIENT_A_NODE}:~/build_mcperf.sh"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "ubuntu@${CLIENT_A_NODE}" -- "chmod +x ~/build_mcperf.sh && ~/build_mcperf.sh && nohup ${CLIENT_A_CMD} > /dev/null 2>&1 &"

echo "sshed into client agent A"

rsync -avz -e "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b --" "./scripts/part3/build_mcperf.sh" "ubuntu@${CLIENT_B_NODE}:~/build_mcperf.sh"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "ubuntu@${CLIENT_B_NODE}" -- "chmod +x ~/build_mcperf.sh && ~/build_mcperf.sh && nohup ${CLIENT_B_CMD} > /dev/null 2>&1 &"

echo "sshed into client agent B"

rsync -avz -e "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b --" "./scripts/part3/build_mcperf.sh" "ubuntu@${CLIENT_MEASURE_NODE}:~/build_mcperf.sh"
gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b "ubuntu@${CLIENT_MEASURE_NODE}" -- "chmod +x ~/build_mcperf.sh && ~/build_mcperf.sh && nohup bash -c '${CLIENT_MEASURE_CMD}' > /dev/null 2>&1 &"

echo "sshed into client measure node and started measurement client"
sleep 10
echo "==============================================================="
echo "Client agents and measurement client are set up and running benchmarks against memcached"
echo "$(gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b -- "ubuntu@${CLIENT_MEASURE_NODE}" -- cat measurements.txt)"
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
    kubectl wait --for=condition=complete job/parsec-canneal --timeout=6000s
    echo "canneal completed, starting vips"
    kubectl create -f "parsec-benchmarks/part3/parsec-vips.yaml" # 4 threads, colocated on node-a-8core
    kubectl wait --for=condition=complete job/parsec-vips --timeout=6000s
}

run_barnes() {
    kubectl wait --for=condition=complete job/parsec-freqmine --timeout=6000s
    echo "freqmine completed, starting barnes"
    kubectl create -f "parsec-benchmarks/part3/parsec-barnes.yaml" # 4 threads, colocated on node-a-8core
    kubectl wait --for=condition=complete job/parsec-barnes --timeout=6000s
}

run_radix() {
    kubectl wait --for=condition=complete job/parsec-blackscholes --timeout=6000s
    kubectl wait --for=condition=complete job/parsec-streamcluster --timeout=6000s
    echo "blackscholes and streamcluster completed, starting radix"
    kubectl create -f "parsec-benchmarks/part3/parsec-radix.yaml" # 1 thread
    kubectl wait --for=condition=complete job/parsec-radix --timeout=6000s
}




for i in {1..3}; do
    #static schedule based on info from part 1,2 results, no kubectl affinity or resource requests/limits
    VERSION=1 

    # colocated with memcached on node-b-4core
    kubectl create -f "parsec-benchmarks/part3/parsec-blackscholes.yaml" # one thread
    kubectl create -f "parsec-benchmarks/part3/parsec-streamcluster.yaml" # two threads
    echo "created blackscholes and streamcluster, waiting for them to complete before starting the next jobs"


    # colocated on node-a-8core
    kubectl create -f "parsec-benchmarks/part3/parsec-canneal.yaml" # 4 threads
    kubectl create -f "parsec-benchmarks/part3/parsec-freqmine.yaml" # 4 threads
    echo "created canneal and freqmine, waiting for them to complete before starting the next jobs"

    run_vips &
    run_barnes &
    run_radix &


    wait
    kubectl get pods -o json > "results/part3/version_${VERSION}run${i}.json"
    echo "All jobs completed for version ${VERSION} run ${i}, collecting logs and cleaning up"

    for job in "${ALL_JOBS[@]}"; do
            kubectl logs job/"$job" > "results/part3/version_${VERSION}_${job}_${i}.txt"
    done
    kubectl delete jobs --all --ignore-not-found
    sleep 5
done

rsync -avz -e "gcloud compute ssh --ssh-key-file ~/.ssh/cloud-computing --zone europe-west1-b --" "ubuntu@${CLIENT_MEASURE_NODE}:~/measurements.txt ./results/part3/version_${VERSION}_measurements.txt" 


