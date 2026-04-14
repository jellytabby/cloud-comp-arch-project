#!/usr/bin/env bash

set -euo pipefail

kops create -f part3.yaml
echo "=============================================================="
echo "Cluster configuration created."
echo "=============================================================="

kops create secret --name part3.k8s.local sshpublickey admin -i ~/.ssh/cloud-computing.pub
echo "=============================================================="
echo "SSH key added to cluster configuration."
echo "=============================================================="

kops update cluster --name part3.k8s.local --yes --admin
echo "=============================================================="
echo "Cluster updated and applied."
echo "=============================================================="

kops validate cluster --wait 10m part3.k8s.local
echo "==============================================================="
echo "Cluster validation completed successfully."
echo "==============================================================="

kubectl get nodes -o wide


