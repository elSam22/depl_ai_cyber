#!/usr/bin/env bash
# Suit en direct les requêtes reçues par notre API (Cloud Logging, cluster GKE dss-cluster).
# À lancer dans Google Cloud Shell (gcloud et kubectl y sont déjà installés et authentifiés).
#
# Prérequis : un compte avec le rôle IAM "Logs Viewer" (roles/logging.viewer) au moins
# sur le projet GCP qui héberge dss-cluster.
#
# Usage :
#   ./voir_requetes.sh <project-id>            # suivi en direct (Ctrl+C pour arrêter)
#   ./voir_requetes.sh <project-id> --depuis 1h # relire la dernière heure puis s'arrêter
#
# Ce qu'on voit : des lignes `score=X longueur=Y duree_ms=Z`. Jamais le texte du commentaire
# ni l'adresse IP de l'appelant (minimisation RGPD, voir DOCUMENTATION.md § 4.1.6/4.1.9).
set -euo pipefail

PROJECT_ID="${1:?Usage : ./voir_requetes.sh <project-id> [--depuis <durée, ex: 1h>]}"
CLUSTER="${CLUSTER:-dss-cluster}"
CONTENEUR="${CONTENEUR:-api}"

gcloud config set project "$PROJECT_ID" >/dev/null

FILTRE="resource.type=\"k8s_container\" AND resource.labels.cluster_name=\"$CLUSTER\" AND resource.labels.container_name=\"$CONTENEUR\""

if [[ "${2:-}" == "--depuis" ]]; then
  DUREE="${3:?Préciser une durée après --depuis, ex: 1h, 30m}"
  echo "Requêtes sur $CLUSTER/$CONTENEUR depuis $DUREE :"
  gcloud logging read "$FILTRE" --project "$PROJECT_ID" --freshness="$DUREE" \
    --order=asc --format='table(timestamp.date("%H:%M:%S"), textPayload)'
  exit 0
fi

echo "Suivi en direct des requêtes sur $CLUSTER/$CONTENEUR (Ctrl+C pour arrêter)..."

# `gcloud logging tail` est en alpha/beta selon les installations de Cloud Shell.
# On essaie alpha, puis beta, puis on replie sur une relecture répétée toutes les 5 s.
if gcloud components list --filter="id:alpha" --format='value(state.name)' 2>/dev/null | grep -qi installed \
   || gcloud alpha --help >/dev/null 2>&1; then
  exec gcloud alpha logging tail "$FILTRE" --project "$PROJECT_ID" \
    --format='value(timestamp.date("%H:%M:%S"), textPayload)'
fi

echo "(gcloud alpha indisponible : relecture toutes les 5 s à la place du vrai direct)"
DEPUIS="$(date -u +%Y-%m-%dT%H:%M:%S.000000Z -d '-5 seconds' 2>/dev/null || date -u -v-5S +%Y-%m-%dT%H:%M:%S.000000Z)"
while true; do
  FILTRE_FENETRE="$FILTRE AND timestamp>\"$DEPUIS\""
  LIGNES="$(gcloud logging read "$FILTRE_FENETRE" --project "$PROJECT_ID" \
             --order=asc --format='value(timestamp, textPayload)')"
  if [[ -n "$LIGNES" ]]; then
    echo "$LIGNES"
    DEPUIS="$(tail -n1 <<< "$LIGNES" | cut -f1)"
  fi
  sleep 5
done
