"""API locale « Digital Social Score » : reçoit un texte, renvoie un score de toxicité de 0 à 100.

Lancement (depuis la racine du projet) :
    .venv/bin/uvicorn api.main:app --port 8000
Documentation interactive (pour tester dans le navigateur) : http://127.0.0.1:8000/docs

RGPD : le texte reçu n'est ni enregistré ni écrit dans les logs. Il est anonymisé avant d'être donné au modèle.
"""
import time
from contextlib import asynccontextmanager
from typing import Literal

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api import modeles
from api.preprocess import pretraiter_detail

@asynccontextmanager
async def demarrage(_app):
    """Au démarrage : charge les modèles rapides disponibles, pour que la première requête ne soit pas lente (~15 s).
    LAYA n'est pas préchargé (800 Mo, ~1 minute) : il se charge à sa première utilisation."""
    for nom, present in modeles.disponibles().items():
        if present and nom != "laya":
            try:
                modeles.obtenir(nom)
            except modeles.ModeleIndisponible:
                pass
    yield


app = FastAPI(title="Digital Social Score (local)", version="0.1", lifespan=demarrage)

# CORS : le front peut aussi appeler une API distante / être ouvert depuis un autre domaine
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PAGE = Path(__file__).resolve().parent.parent / "front" / "index.html"

SEUIL_PAR_DEFAUT = 0.5


class Requete(BaseModel):
    texte: str = Field(min_length=1, max_length=5000, description="Commentaire à analyser")
    modele: Literal["bilstm", "distilbert", "laya"] = Field("distilbert", description="Modèle à utiliser (laya est lent)")
    anonymiser: bool = Field(True, description="Anonymiser le texte avant la prédiction (comme à l'entraînement)")


def score_label(proba: float) -> float:
    """Score d'un label = probabilité du label x 100 (de 0 à 100)."""
    return round(min(max(proba * 100, 0.0), 100.0), 1)


def score_global(labels: dict) -> float:
    """Score global de 0 à 100.

    - si au moins un label est détecté (probabilité >= son seuil) :
      moyenne des scores (probabilité x 100) des labels détectés ;
    - sinon : score du label `toxic`.
    """
    detectes = [v["score"] for v in labels.values() if v["detecte"]]
    if detectes:
        return round(sum(detectes) / len(detectes), 1)
    return labels["toxic"]["score"]


@app.get("/", include_in_schema=False)
def accueil():
    """Sert la page de démonstration (front/index.html)."""
    return FileResponse(PAGE)


@app.get("/sante")
def sante():
    """Vérifie que l'API tourne et indique quels modèles sont disponibles."""
    return {"statut": "ok", "modeles_disponibles": modeles.disponibles()}


@app.post("/predire")
def predire(requete: Requete):
    try:
        modele = modeles.obtenir(requete.modele)
    except modeles.ModeleIndisponible as e:
        raise HTTPException(status_code=503, detail=f"Modèle « {requete.modele} » indisponible : {e}")

    t0 = time.perf_counter()                       # chronomètre démarré après le chargement éventuel du modèle
    etapes = pretraiter_detail(requete.texte, requete.anonymiser)
    texte_traite = etapes["nettoye"]
    t_pre = time.perf_counter()
    probas = modele.probabilites(texte_traite)
    t_mod = time.perf_counter()

    seuils = modeles.seuils(modele)
    avertissement = None
    if seuils is None:
        seuils = {l: SEUIL_PAR_DEFAUT for l in modeles.LABELS}
        avertissement = "seuils non trouvés (models/seuils.json) : seuil 0,5 utilisé pour tous les labels"

    labels = {}
    for label, p in zip(modeles.LABELS, probas):
        s = seuils.get(label, SEUIL_PAR_DEFAUT)
        labels[label] = {"probabilite": round(float(p), 4), "seuil": round(float(s), 2),
                         "score": score_label(float(p)), "detecte": bool(p >= s)}

    return {
        "modele": requete.modele,
        "score_global": score_global(labels),
        "toxique": any(v["detecte"] for v in labels.values()),
        "labels": labels,
        "etapes": etapes,                                            # original / masques / anonymise / nettoye (animation du front)
        "texte_traite": texte_traite,                                # texte anonymisé et nettoyé vu par le modèle
        "avertissement": avertissement,
        "temps_pretraitement_ms": round(1000 * (t_pre - t0), 1),   # anonymisation + nettoyage (hors chargement du modèle)
        "temps_modele_ms": round(1000 * (t_mod - t_pre), 1),      # « réflexion » du modèle
        "temps_ms": round(1000 * (time.perf_counter() - t0), 1),   # total côté API
    }
