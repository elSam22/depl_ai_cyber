"""API Digital Social Score : reçoit un texte, renvoie un verdict de toxicité.

Flux d'une requête : clé API -> validation -> anonymisation -> nettoyage -> modèle -> score.
Le texte reçu n'est jamais journalisé ni stocké.
Réponse volontairement minimale (toxique oui/non) : le score, les probabilités, les seuils
et la version du modèle restent internes (logs/métriques) pour ne pas aider un attaquant à
régler une évasion ni à extraire le modèle.
"""
import logging
import os
import secrets
import time

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from prometheus_client import start_http_server
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from preprocessing import PREPROCESSING_VERSION, preprocess
from scorer import LABELS, load_scorer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dss")

# --- Chargés UNE fois au démarrage (modèle spaCy via l'import de preprocessing, puis le modèle)
scorer = load_scorer()
API_KEY = os.environ.get("API_KEY")          # injectée depuis Secret Manager (Secret Kubernetes), jamais dans le code
MAX_CHARS = int(os.environ.get("MAX_CHARS", "5000"))

# Doc publique désactivée (docs_url/redoc_url/openapi_url = None) : ne pas exposer le schéma
# complet de l'API à un attaquant non authentifié.
# Prod : doc fermée. Dev/staging : doc ouverte. Piloté par la variable d'env ENV.
EST_PROD = os.environ.get("ENV", "dev").lower() == "prod"

app = FastAPI(
    title="Digital Social Score API",
    description="Score de toxicité d'un texte. Le texte reçu est anonymisé et n'est jamais stocké.",
    version="1.0.0",
    docs_url=None if EST_PROD else "/docs",
    redoc_url=None if EST_PROD else "/redoc",
    openapi_url=None if EST_PROD else "/openapi.json",
)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# --- Supervision (étape 6) : métriques Prometheus (requêtes, erreurs, latence par route).
# Servies sur un port SÉPARÉ (9090), pas sur /metrics : le Service et l'Ingress n'exposent que le port 8080,
# donc les métriques ne sont pas publiques. Prometheus les lit directement sur le pod (PodMonitor).
# /health est exclu (appelé en continu par les sondes Kubernetes). METRICS_PORT=0 désactive (tests).
Instrumentator(excluded_handlers=["/health"]).instrument(app)
_port_metriques = int(os.environ.get("METRICS_PORT", "9090"))
if _port_metriques:
    start_http_server(_port_metriques)


def verifier_cle(cle: str | None = Security(api_key_header)) -> None:
    """Refuse la requête si la clé API est absente ou fausse (401)."""
    if API_KEY is None:
        raise HTTPException(status_code=500, detail="API_KEY non configurée sur le serveur")
    if cle is None or not secrets.compare_digest(cle, API_KEY):   # comparaison à temps constant
        raise HTTPException(status_code=401, detail="Clé API absente ou invalide")


class Demande(BaseModel):
    # Validation d'entrée : FastAPI renvoie 422 si le texte est absent, vide ou trop long
    text: str = Field(..., min_length=1, max_length=MAX_CHARS, description="Texte à évaluer")


class Reponse(BaseModel):
    # Réponse minimale : uniquement le verdict. Le détail (score, labels, seuils, version)
    # reste interne pour ne pas donner de signal exploitable à un attaquant.
    toxique: bool = Field(..., description="Au moins un label dépasse son seuil de décision")


@app.get("/health")
def health():
    """Sonde de vie (load balancer, Kubernetes) : statut seul, sans révéler les versions."""
    return {"status": "ok"}


@app.post("/score", response_model=Reponse, dependencies=[Depends(verifier_cle)])
def score(demande: Demande):
    if not demande.text.strip():
        raise HTTPException(status_code=422, detail="Texte vide")

    t0 = time.perf_counter()
    texte = preprocess(demande.text)            # MÊME traitement qu'à l'entraînement (inclut la normalisation anti-évasion)
    probas = scorer.predict([texte])[0]
    duree_ms = 1000 * (time.perf_counter() - t0)

    detectes = [label for label in LABELS if probas[label] >= scorer.seuils[label]]
    # Score 0-100 (DOCUMENTATION.md §4) : moyenne des labels détectés, sinon probabilité de toxic.
    # Calculé pour le LOG interne et la décision, mais PAS renvoyé au client.
    retenus = detectes or ["toxic"]
    score_final = round(100 * sum(probas[label] for label in retenus) / len(retenus))
    # Log SANS le texte : score, longueur, durée (minimisation RGPD). Le détail reste ici, pas dans la réponse.
    log.info("score=%d longueur=%d duree_ms=%.1f", score_final, len(demande.text), duree_ms)

    return Reponse(toxique=bool(detectes))