#!/usr/bin/env bash
# Construit l'image (Cloud Build) puis la déploie sur le cluster GKE.
# Usage (depuis la racine du repo) :  PROJECT_ID=mon-projet bash api/deploy/deploy_gke.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Définir PROJECT_ID}"
REGION="${REGION:-europe-west9}"
REPO="dss"
TAG="$(git rev-parse --short HEAD 2>/dev/null || echo dev)-$(date +%Y%m%d%H%M%S)"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/dss-api:$TAG"
K8S="$(dirname "$0")/../k8s"

echo "1/3 Construction de l'image $IMAGE (Cloud Build, rien à installer en local)"
gcloud builds submit api --tag "$IMAGE" --project "$PROJECT_ID" --timeout=30m --machine-type=e2-highcpu-8

echo "2/3 Application des manifests Kubernetes"
IP="$(gcloud compute addresses describe dss-ip --global --format='value(address)')"
DOMAIN="${IP//./-}.sslip.io"              # nom de domaine gratuit qui pointe vers l'IP (pour le certificat HTTPS)
sed "s|IMAGE_URL|$IMAGE|" "$K8S/deployment.yaml" | kubectl apply -f -
kubectl apply -f "$K8S/service.yaml" -f "$K8S/hpa.yaml"
sed "s|DOMAIN|$DOMAIN|" "$K8S/ingress.yaml" | kubectl apply -f -

echo "3/3 Attente du déploiement (pods prêts)"
kubectl rollout status deployment/dss-api --timeout=10m

echo
echo "API : https://$DOMAIN"
echo "Le load balancer met ~5 min à répondre, le certificat HTTPS 15 à 60 min la première fois."
echo "Suivi du certificat :  kubectl describe managedcertificate dss-cert"
