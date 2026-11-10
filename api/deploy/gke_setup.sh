#!/usr/bin/env bash
# Mise en place GCP + cluster Kubernetes (une seule fois).
# Usage (depuis la racine du repo) :  PROJECT_ID=mon-projet bash api/deploy/gke_setup.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Définir PROJECT_ID (ex: PROJECT_ID=dss-esigelec bash ...)}"
REGION="${REGION:-europe-west9}"          # Paris : données hébergées dans l'UE (RGPD)
REPO="dss"
CLUSTER="dss-cluster"

gcloud config set project "$PROJECT_ID"

echo "1/6 Activation des APIs"
gcloud services enable container.googleapis.com compute.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com

echo "2/6 Dépôt d'images Docker (Artifact Registry)"
gcloud artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" \
    --description="Images de l'API Digital Social Score"

echo "3/6 Clé API aléatoire stockée dans Secret Manager (jamais dans le code ni dans Git)"
gcloud secrets describe dss-api-key >/dev/null 2>&1 || \
  openssl rand -hex 32 | gcloud secrets create dss-api-key --data-file=- --replication-policy=automatic

echo "4/6 Cluster GKE Autopilot (Google gère les nœuds ; quelques minutes)"
gcloud container clusters describe "$CLUSTER" --region "$REGION" >/dev/null 2>&1 || \
  gcloud container clusters create-auto "$CLUSTER" --region "$REGION"
gcloud container clusters get-credentials "$CLUSTER" --region "$REGION"

echo "5/6 Droit de lecture des images pour les nœuds du cluster (moindre privilège)"
NUM="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
gcloud artifacts repositories add-iam-policy-binding "$REPO" --location="$REGION" \
  --member="serviceAccount:$NUM-compute@developer.gserviceaccount.com" \
  --role="roles/artifactregistry.reader" >/dev/null

echo "6/6 IP publique fixe + Secret Kubernetes contenant la clé API"
gcloud compute addresses describe dss-ip --global >/dev/null 2>&1 || \
  gcloud compute addresses create dss-ip --global
kubectl create secret generic dss-api-key \
  --from-literal=API_KEY="$(gcloud secrets versions access latest --secret=dss-api-key)" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "OK. Clé API (à garder pour vous) :  gcloud secrets versions access latest --secret=dss-api-key"
