#!/usr/bin/env bash

set -euo pipefail

kops create -f part1.yaml
echo "Cluster configuration created."

kops create secret --name part1.k8s.local sshpublickey admin -i ~/.ssh/cloud-computing.pub
echo "SSH key added to cluster configuration."

kops update cluster --name part1.k8s.local --yes --admin
echo "Cluster updated and applied."

kops validate cluster --wait 10m part1.k8s.local
echo "Cluster validation completed successfully."

kubectl get nodes -o wide
