"""API Digital Social Score : reçoit un texte, renvoie un score de toxicité de 0 à 100 et un verdict.

Flux d'une requête : clé API -> validation -> anonymisation -> nettoyage -> modèle -> score.
Le texte reçu n'est jamais journalisé ni stocké.
Réponse volontairement pauvre : le score est ARRONDI À LA DIZAINE (défense contre le vol de modèle par distillation,
voir defense_extraction.py) et accompagné du verdict. Les probabilités, les seuils et les textes prétraités restent
internes (logs/métriques) : ils aideraient un attaquant à régler une évasion ou à extraire le modèle.
"""
import asyncio
import logging
import os
import secrets
import time

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from prometheus_client import start_http_server
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from pydantic import BaseModel, Field

from defense_extraction import quantifier_score
from preprocessing import PREPROCESSING_VERSION, preprocess
from protection import ECHECS, Protection, ip_client, journaliser_refus
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
# Protection en entrée (limites par IP, clés fausses, taille du corps, en-têtes de sécurité). Ajoutée AVANT le CORS :
# le dernier middleware ajouté est le plus externe, donc les refus 429/413 portent aussi les en-têtes CORS.
app.add_middleware(Protection)
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
# Intervalles de latence élargis jusqu'à 10 s (par défaut 1 s : le P95 restait bloqué à 1 s, alerte « P95 > 2 s » impossible).
Instrumentator(excluded_handlers=["/health"]).add(
    metrics.default(latency_lowr_buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10))
).instrument(app)
_port_metriques = int(os.environ.get("METRICS_PORT", "9090"))
if _port_metriques:
    start_http_server(_port_metriques)


async def verifier_cle(request: Request, cle: str | None = Security(api_key_header)) -> None:
    """Refuse la requête si la clé API est absente ou fausse (401). Chaque refus est compté par adresse : au-delà de
    LIMITE_ECHECS_PAR_MIN, Protection bloque l'adresse (anti brute-force) et le refus est journalisé sans la clé."""
    if API_KEY is None:
        raise HTTPException(status_code=500, detail="API_KEY non configurée sur le serveur")
    # Comparaison à temps constant, sur des OCTETS : compare_digest refuse les chaînes non ASCII (TypeError -> erreur 500,
    # test S2b) ; une clé avec un accent doit simplement être refusée (401) et comptée comme clé fausse.
    if cle is None or not secrets.compare_digest(cle.encode(), API_KEY.encode()):
        ip = ip_client(request.scope)
        ECHECS.enregistrer(ip)
        journaliser_refus("cle_invalide", request.url.path, ip)
        raise HTTPException(status_code=401, detail="Clé API absente ou invalide")


class Demande(BaseModel):
    # Validation d'entrée : FastAPI renvoie 422 si le texte est absent, vide ou trop long
    text: str = Field(..., min_length=1, max_length=MAX_CHARS, description="Texte à évaluer")


class Reponse(BaseModel):
    # Réponse volontairement pauvre : score arrondi à la dizaine + verdict. Le détail (probabilités, seuils, textes
    # prétraités) reste interne pour ne pas donner de signal exploitable à un attaquant.
    score: int = Field(..., ge=0, le=100, description="Score de toxicité 0-100, arrondi à la dizaine")
    toxique: bool = Field(..., description="Au moins un label dépasse son seuil de décision")


@app.get("/health")
async def health():
    """Sonde de vie (load balancer, Kubernetes) : statut seul, sans révéler les versions."""
    return {"status": "ok"}


@app.get("/version", dependencies=[Depends(verifier_cle)])
async def version():
    """Version du modèle, RÉSERVÉE à la clé : le contrôle après déploiement s'en sert pour refuser le modèle factice
    (« dummy-… »), sans révéler la version à un client non authentifié."""
    return {"model_version": scorer.version, "preprocessing_version": PREPROCESSING_VERSION}


# Au plus MAX_INFERENCES calculs en même temps par pod (1 CPU) ; une requête de plus attend ATTENTE_MAX_S au plus, puis
# reçoit 503. Sans cela, la latence monte de ×76 (chez nous, rapport du professeur) à ×108 (autres équipes) : mieux vaut
# refuser vite que répondre en 30 s. Attente ramenée de 1 s à 0,25 s : une requête acceptée attend au plus 0,25 s.
INFERENCES = asyncio.Semaphore(int(os.environ.get("MAX_INFERENCES", "3")))
ATTENTE_MAX_S = float(os.environ.get("ATTENTE_MAX_S", "0.25"))


def _evaluer(texte_brut: str) -> Reponse:
    t0 = time.perf_counter()
    texte = preprocess(texte_brut)              # MÊME traitement qu'à l'entraînement (inclut la normalisation anti-évasion)
    probas = scorer.predict([texte])[0]
    duree_ms = 1000 * (time.perf_counter() - t0)

    detectes = [label for label in LABELS if probas[label] >= scorer.seuils[label]]
    # Score 0-100 (DOCUMENTATION.md §4) : moyenne des labels détectés, sinon probabilité de toxic.
    # Calculé pour le LOG interne et la décision, mais PAS renvoyé au client.
    retenus = detectes or ["toxic"]
    score_final = round(100 * sum(probas[label] for label in retenus) / len(retenus))
    # Log SANS le texte : score, longueur, durée (minimisation RGPD). Le détail reste ici, pas dans la réponse.
    log.info("score=%d longueur=%d duree_ms=%.1f", score_final, len(texte_brut), duree_ms)
    return Reponse(score=quantifier_score(score_final), toxique=bool(detectes))


@app.post("/score", response_model=Reponse, dependencies=[Depends(verifier_cle)])
async def score(demande: Demande, request: Request):
    if not demande.text.strip():
        raise HTTPException(status_code=422, detail="Texte vide")
    try:
        await asyncio.wait_for(INFERENCES.acquire(), ATTENTE_MAX_S)
    except asyncio.TimeoutError:
        journaliser_refus("surcharge", "/score", ip_client(request.scope))
        raise HTTPException(status_code=503, detail="Service saturé, réessayer", headers={"Retry-After": "1"})
    try:
        return await run_in_threadpool(_evaluer, demande.text)   # hors de la boucle : /health reste réactif
    finally:
        INFERENCES.release()
