#!/usr/bin/env bash
# Construit l'image (Cloud Build) puis la déploie sur le cluster GKE.
# Usage (depuis la racine du repo) :  PROJECT_ID=mon-projet bash api/deploy/deploy_gke.sh
set -euo pipefail
# Avant de lancer : python api/export_model.py --type distilbert  puis  chmod a+r api/model/*  (les poids ne sont pas dans Git)

PROJECT_ID="${PROJECT_ID:?Définir PROJECT_ID}"
REGION="${REGION:-europe-west9}"
REPO="dss"
TAG="$(git rev-parse --short HEAD 2>/dev/null || echo dev)-$(date +%Y%m%d%H%M%S)"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/dss-api:$TAG"
K8S="$(dirname "$0")/../k8s"

echo "1/3 Construction de l'image $IMAGE (Cloud Build, rien à installer en local)"
# On fabrique et envoie nous-mêmes l'archive des sources, puis on construit depuis cette archive : « gcloud builds submit api »
# interroge le bucket de sources d'une façon que le compte fédéré de la pipeline (sans clé) n'a pas le droit de faire.
# Mêmes exclusions que api/.gcloudignore (le dossier model/ avec les poids EST inclus).
SOURCES="gs://${PROJECT_ID}_cloudbuild/source/dss-api-${TAG}.tgz"
ARCHIVE="$(mktemp -t dss-api-XXXXXX).tgz"
COPYFILE_DISABLE=1 tar -czf "$ARCHIVE" -C api \
  --exclude=__pycache__ --exclude='*.pyc' --exclude=./tests --exclude=./deploy --exclude=./export_model.py \
  --exclude=./requirements-dev.txt --exclude=./README.md --exclude=./.pytest_cache --exclude=./pytest.ini --exclude=./k8s .
gcloud storage cp "$ARCHIVE" "$SOURCES" --project "$PROJECT_ID"
rm -f "$ARCHIVE"
# --no-source : même avec une archive déjà dans un bucket, « gcloud builds submit » revérifie ce bucket avec des droits que
# le compte fédéré de la pipeline n'a pas. Le build récupère donc lui-même l'archive (il tourne avec le compte de service
# de Cloud Build, qui y a accès) puis construit l'image avec le Dockerfile.
CONFIG="$(mktemp -t cloudbuild-XXXXXX).yaml"
cat > "$CONFIG" <<'YAML'
steps:
  - name: gcr.io/google.com/cloudsdktool/cloud-sdk
    entrypoint: bash
    args: ["-c", "gcloud storage cp ${_SOURCES} /workspace/src.tgz && tar xzf /workspace/src.tgz -C /workspace"]
  - name: gcr.io/cloud-builders/docker
    args: ["build", "-t", "${_IMAGE}", "."]
images: ["${_IMAGE}"]
options:
  machineType: E2_HIGHCPU_8
timeout: 1800s
YAML
gcloud builds submit --no-source --config "$CONFIG" --substitutions "_SOURCES=$SOURCES,_IMAGE=$IMAGE" --project "$PROJECT_ID"
rm -f "$CONFIG"

echo "2/3 Application des manifests Kubernetes"
IP="$(gcloud compute addresses describe dss-ip --global --format='value(address)')"
DOMAIN="${IP//./-}.sslip.io"              # nom de domaine gratuit qui pointe vers l'IP (pour le certificat HTTPS)
sed "s|IMAGE_URL|$IMAGE|" "$K8S/deployment.yaml" | kubectl apply -f -
kubectl apply -f "$K8S/service.yaml" -f "$K8S/hpa.yaml"
sed "s|DOMAIN|$DOMAIN|" "$K8S/ingress.yaml" | kubectl apply -f -

echo "3/4 Attente du déploiement (pods prêts)"
kubectl rollout status deployment/dss-api --timeout=10m

echo "4/4 Contrôle de l'API déployée (modèle réel, authentification)"
API_KEY="$(gcloud secrets versions access latest --secret=dss-api-key --project "$PROJECT_ID")" \
  python3 "$(dirname "$0")/verifier_deploiement.py" "https://$DOMAIN" \
  || { echo "CONTRÔLE ÉCHOUÉ : revenir en arrière avec  kubectl rollout undo deployment/dss-api"; exit 1; }

echo
echo "API : https://$DOMAIN"
echo "Le load balancer met ~5 min à répondre, le certificat HTTPS 15 à 60 min la première fois."
echo "Suivi du certificat :  kubectl describe managedcertificate dss-cert"
