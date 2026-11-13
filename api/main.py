"""API Digital Social Score : reçoit un texte, renvoie un score de toxicité de 0 à 100.

Flux d'une requête : clé API -> validation -> anonymisation -> nettoyage -> modèle -> score.
Le texte reçu n'est jamais journalisé ni stocké.
"""
import logging
import os
import secrets
import time

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
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

app = FastAPI(
    title="Digital Social Score API",
    description="Score de toxicité (0-100) d'un texte. Le texte reçu est anonymisé et n'est jamais stocké.",
    version="1.0.0",
)
# CORS : le front de démonstration appelle l'API depuis le navigateur (page ouverte depuis un fichier, origine « null »).
# Pas de cookies (la clé est dans l'en-tête X-API-Key) : "*" sans credentials ne réduit pas la sécurité de la clé.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
    allow_credentials=False,
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
    score: int = Field(..., ge=0, le=100,
                       description="Moyenne x 100 des labels détectés, sinon probabilité de toxic x 100")
    labels: dict[str, float]
    toxique: bool = Field(..., description="Au moins un label dépasse son seuil de décision")
    labels_detectes: list[str] = Field(..., description="Labels dont la probabilité dépasse le seuil")
    seuils: dict[str, float] = Field(..., description="Seuils de décision du modèle, calibrés sur la validation")
    model_version: str


@app.get("/health")
def health():
    """Sonde de vie (load balancer, Kubernetes)."""
    return {"status": "ok", "model_version": scorer.version, "preprocessing_version": PREPROCESSING_VERSION}


@app.post("/score", response_model=Reponse, dependencies=[Depends(verifier_cle)])
def score(demande: Demande):
    if not demande.text.strip():
        raise HTTPException(status_code=422, detail="Texte vide")

    t0 = time.perf_counter()
    texte = preprocess(demande.text)            # MÊME traitement qu'à l'entraînement
    probas = scorer.predict([texte])[0]
    duree_ms = 1000 * (time.perf_counter() - t0)

    detectes = [label for label in LABELS if probas[label] >= scorer.seuils[label]]
    # Score 0-100 (DOCUMENTATION.md §4) : moyenne des labels détectés, sinon probabilité de toxic
    retenus = detectes or ["toxic"]
    score_final = round(100 * sum(probas[label] for label in retenus) / len(retenus))
    # Log SANS le texte : longueur, score, durée (minimisation RGPD)
    log.info("score=%d longueur=%d duree_ms=%.1f", score_final, len(demande.text), duree_ms)
    return Reponse(
        score=score_final,
        labels={label: round(probas[label], 4) for label in LABELS},
        toxique=bool(detectes),
        labels_detectes=detectes,
        seuils=scorer.seuils,
        model_version=scorer.version,
    )