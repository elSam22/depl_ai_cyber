#!/usr/bin/env bash
# Contrôle des coûts (crédits étudiants). Autopilot facture les pods tant qu'ils tournent.
#   bash api/deploy/gke_pause.sh stop    -> 0 pod (HPA retiré), presque plus rien à payer
#   bash api/deploy/gke_pause.sh start   -> 2 pods + autoscaling
# Fin du projet :  gcloud container clusters delete dss-cluster --region europe-west9
#                  gcloud compute addresses delete dss-ip --global
set -euo pipefail
K8S="$(dirname "$0")/../k8s"
case "${1:-}" in
  stop)  kubectl delete -f "$K8S/hpa.yaml" --ignore-not-found
         kubectl scale deployment/dss-api --replicas=0 ;;
  start) kubectl scale deployment/dss-api --replicas=2
         kubectl apply -f "$K8S/hpa.yaml" ;;
  *)     echo "Usage : $0 stop|start"; exit 1 ;;
esac
kubectl get pods
