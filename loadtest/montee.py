"""Profil « montée progressive » : 1 -> 10 -> 50 -> 100 utilisateurs sur 5 minutes.

À utiliser avec le locustfile (même commande, deux fichiers) :
    API_KEY=... .venv/bin/locust -f loadtest/locustfile.py,loadtest/montee.py --host https://<url> \
        --headless --csv loadtest/results/montee

Chaque palier dure assez longtemps pour mesurer la latence une fois le régime établi.
Les chiffres par palier sont dans `<préfixe>_stats_history.csv` (une ligne par seconde) : report.py les découpera.
"""
from locust import LoadTestShape

# (fin du palier en secondes depuis le début, nombre d'utilisateurs)
PALIERS = [
    (45, 1),      # palier 1 : 1 utilisateur (référence)
    (105, 10),    # palier 2 : 10 utilisateurs
    (195, 50),    # palier 3 : 50 utilisateurs
    (300, 100),   # palier 4 : 100 utilisateurs
]
VITESSE_ARRIVEE = 10   # nouveaux utilisateurs par seconde pendant la transition entre deux paliers


class MonteeProgressive(LoadTestShape):
    def tick(self):
        t = self.get_run_time()
        for fin, utilisateurs in PALIERS:
            if t < fin:
                return utilisateurs, VITESSE_ARRIVEE
        return None   # fin du test
