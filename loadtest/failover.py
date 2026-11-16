"""Profil « failover » : charge constante de 5 utilisateurs pendant 4 minutes.

Pendant ce temps, on supprime UN pod de l'API à la main (voir loadtest/RAPPORT.md) pour voir si le service continue.
5 utilisateurs ≈ 5 requêtes/s : sous la capacité de 2 pods (≈ 8 requêtes/s), donc le service est sain AVANT l'incident,
et on voit clairement l'effet de la perte d'un pod.

Lancement :
    API_KEY=... LOG_REQUETES=loadtest/results/failover_requetes.csv .venv/bin/locust \
        -f loadtest/locustfile.py,loadtest/failover.py --host https://<url> --web-host 127.0.0.1 --csv loadtest/results/failover
"""
from locust import LoadTestShape

UTILISATEURS = 5
DUREE_S = 240


class ChargeConstante(LoadTestShape):
    def tick(self):
        if self.get_run_time() < DUREE_S:
            return UTILISATEURS, UTILISATEURS      # tous les utilisateurs arrivent en 1 seconde
        return None
