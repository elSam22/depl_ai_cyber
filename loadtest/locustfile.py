"""Test de charge de l'API Digital Social Score (étape 5 du TP).

Chaque utilisateur simulé envoie en boucle un commentaire à POST /score, puis attend un court instant.

Configuration par variables d'environnement (rien n'est écrit dans un fichier ni dans Git) :
    API_KEY   clé de l'API (en-tête X-API-Key)                       [obligatoire]
    PAUSE_S   pause entre deux requêtes d'un utilisateur, en secondes [défaut 0.5]
    LOG_REQUETES   (facultatif) fichier CSV : une ligne par requête (heure, durée en ms, code HTTP).
                   Sert à calculer de vrais percentiles par palier. Aucun texte ni clé n'y est écrit.

Lancement (depuis la racine du projet) :
    API_KEY=... .venv/bin/locust -f loadtest/locustfile.py --host https://<url> \
        --headless -u 1 -r 1 -t 60s --csv loadtest/results/reference
ou, avec l'interface web (graphiques en direct) : retirer --headless ... et ouvrir http://localhost:8089
"""
import os
import random
import time
from pathlib import Path

import pandas as pd
from locust import HttpUser, between, events, task

CSV_TEXTES = Path(__file__).resolve().parent.parent / "data" / "clean" / "test_clean.csv"
N_TEXTES = 1000                 # échantillon de textes variés (courts et longs), tirés avec une graine fixe
LONGUEUR_MAX = 5000             # limite de validation de l'API : au-delà, la réponse serait 422

TEXTES: list[str] = []
_journal = None                 # fichier de journal par requête (facultatif)


@events.init.add_listener
def charger_textes(environment, **_kwargs):
    """Charge une fois l'échantillon de textes (même échantillon à chaque lancement)."""
    if not os.environ.get("API_KEY"):
        raise SystemExit("Définir la variable d'environnement API_KEY")
    df = pd.read_csv(CSV_TEXTES, usecols=["comment_text"]).dropna()
    df = df[df["comment_text"].str.strip().str.len().between(1, LONGUEUR_MAX)]
    TEXTES.extend(df.sample(N_TEXTES, random_state=42)["comment_text"].tolist())
    longueurs = pd.Series([len(t) for t in TEXTES])
    print(f"{len(TEXTES)} textes chargés (longueur médiane {longueurs.median():.0f}, max {longueurs.max()})")


@events.request.add_listener
def journaliser(request_type, name, response_time, response_length, exception, context=None, **_kwargs):
    """Une ligne par requête : heure (s), durée (ms), échec (0/1). Jamais le texte envoyé."""
    global _journal
    chemin = os.environ.get("LOG_REQUETES")
    if not chemin:
        return
    if _journal is None:
        _journal = open(chemin, "w", encoding="utf-8", buffering=1)
        _journal.write("heure_s,duree_ms,echec\n")
    _journal.write(f"{time.time():.3f},{response_time:.0f},{int(exception is not None)}\n")


class Utilisateur(HttpUser):
    wait_time = between(float(os.environ.get("PAUSE_S", "0.5")), float(os.environ.get("PAUSE_S", "0.5")) + 0.5)

    @task
    def score(self):
        # Un texte différent à chaque requête : évite qu'un cache fausse les mesures
        self.client.post(
            "/score",
            json={"text": random.choice(TEXTES)},
            headers={"X-API-Key": os.environ["API_KEY"]},
            name="POST /score",
        )
