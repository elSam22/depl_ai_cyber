"""Test de charge (étape 5).  Usage :
    API_KEY=<clé> locust -f api/tests/locustfile.py --host https://<url-cloud-run>
puis ouvrir http://localhost:8089 (ou --headless -u 50 -r 5 -t 3m --csv rapport).
"""
import os
import random

from locust import HttpUser, between, task

TEXTES = [
    "Thanks for fixing the references, great work.",
    "You are a complete idiot, stop editing this page.",
    "I disagree with this edit, please discuss it on the talk page first.",
    "Go away, nobody wants you here.",
]


class Utilisateur(HttpUser):
    wait_time = between(0.5, 2)

    @task
    def score(self):
        self.client.post("/score", json={"text": random.choice(TEXTES)},
                         headers={"X-API-Key": os.environ["API_KEY"]})
