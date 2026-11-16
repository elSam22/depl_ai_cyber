"""Simulation d'attaque (étape 6) : des « attaquants » envoient des requêtes invalides pendant que des utilisateurs légitimes
continuent d'utiliser l'API. On mesure si le service légitime tient (continuité de service).

NE PAS LANCER SANS PRÉVENIR l'équipe : cela charge le cluster partagé (crédit). Rester à faible intensité.

Les attaques sont attendues et refusées par l'API : un 401 ou un 422 est donc un SUCCÈS ici (la défense a fonctionné) ;
les requêtes sont nommées « ATTAQUE … » pour les séparer des requêtes « LEGITIME » dans les résultats.

Variables d'environnement : API_KEY (clé valide, utilisée par les utilisateurs légitimes uniquement).
Lancement (exemple : 5 légitimes + 20 attaquants, 2 minutes) :
    API_KEY=... .venv/bin/locust -f loadtest/locustfile.py,loadtest/attaque.py --host https://<url> \
        --headless -u 25 -r 5 -t 2m --csv loadtest/results/attaque Legitime Attaquant
Remarque : `locustfile.py` (journal par requête, LOG_REQUETES) définit aussi la classe `Utilisateur` ; on nomme ici les deux classes à lancer pour l'exclure.
"""
import json
import os
import random

from locust import HttpUser, between, task

# Quelques textes fixes : pour tester la continuité de service, la variété des textes n'a pas d'importance
TEXTES = ["Thanks for fixing the references, great work.", "You are a complete idiot, stop editing this page.",
          "I disagree with this edit, please discuss it on the talk page first.", "Go away, nobody wants you here."]


class Legitime(HttpUser):
    """Utilisateur normal, avec une clé valide."""
    weight = 1
    wait_time = between(0.5, 1.0)

    @task
    def score(self):
        self.client.post("/score", json={"text": random.choice(TEXTES)},
                         headers={"X-API-Key": os.environ["API_KEY"]}, name="LEGITIME /score")


class Attaquant(HttpUser):
    """Envoie des requêtes que l'API doit refuser rapidement."""
    weight = 4
    wait_time = between(0.05, 0.2)

    def _attendre(self, chemin, code_attendu, nom, **kwargs):
        with self.client.post(chemin, name=nom, catch_response=True, **kwargs) as r:
            if r.status_code == code_attendu:
                r.success()                                   # la défense a fonctionné
            else:
                r.failure(f"attendu {code_attendu}, reçu {r.status_code}")

    @task(5)
    def sans_cle(self):
        self._attendre("/score", 401, "ATTAQUE sans clé", json={"text": "hello"})

    @task(3)
    def mauvaise_cle(self):
        self._attendre("/score", 401, "ATTAQUE mauvaise clé", json={"text": "hello"},
                       headers={"X-API-Key": "".join(random.choices("0123456789abcdef", k=64))})

    @task(1)
    def texte_trop_long(self):
        self._attendre("/score", 422, "ATTAQUE texte trop long", data=json.dumps({"text": "a" * 6000}),
                       headers={"Content-Type": "application/json", "X-API-Key": os.environ["API_KEY"]})

    @task(1)
    def json_invalide(self):
        self._attendre("/score", 422, "ATTAQUE json invalide", data="pas du json",
                       headers={"Content-Type": "application/json", "X-API-Key": os.environ["API_KEY"]})
