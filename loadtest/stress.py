"""Profil « stress » : on ajoute des utilisateurs jusqu'au point de rupture, puis le test s'arrête tout seul.

Toutes les PAS_DUREE_S secondes, on ajoute PAS_UTILISATEURS utilisateurs (10, 20, 30...). Le test s'arrête dès que :
  - le P95 de la latence (sur les 10 dernières secondes) reste au-dessus de SEUIL_P95_MS pendant SOUTENU_S secondes, ou
  - SEUIL_ERREURS erreurs ou plus apparaissent en 10 secondes, ou
  - MAX_UTILISATEURS est atteint et tenu pendant un palier (aucune rupture : l'API a tenu).
Le point de rupture (nombre d'utilisateurs, heure, cause) est écrit dans loadtest/results/stress_rupture.json.

Lancement :
    API_KEY=... LOG_REQUETES=loadtest/results/stress_requetes.csv .venv/bin/locust \
        -f loadtest/locustfile.py,loadtest/stress.py --host https://<url> --web-host 127.0.0.1 --csv loadtest/results/stress
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from locust import LoadTestShape

PAS_UTILISATEURS = 10
PAS_DUREE_S = 20
MAX_UTILISATEURS = 200
SEUIL_P95_MS = 2000
SOUTENU_S = 10
SEUIL_ERREURS = 5
SORTIE = Path(__file__).resolve().parent / "results" / "stress_rupture.json"


class Stress(LoadTestShape):
    def __init__(self):
        super().__init__()
        self.p95_haut_depuis = None        # instant (s) depuis lequel le P95 dépasse le seuil
        self.erreurs = []                  # (instant, nombre cumulé d'erreurs) pour compter sur 10 s

    def _fin(self, cause, t, utilisateurs, p95):
        SORTIE.write_text(json.dumps({
            "cause": cause, "utilisateurs": utilisateurs, "t_s": round(t),
            "p95_fenetre_ms": round(p95 or 0),
            "heure_utc": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        }, indent=2), encoding="utf-8")
        return None

    def tick(self):
        t = self.get_run_time()
        utilisateurs = min((int(t // PAS_DUREE_S) + 1) * PAS_UTILISATEURS, MAX_UTILISATEURS)
        stats = self.runner.stats.total
        p95 = stats.get_current_response_time_percentile(0.95)

        # 1) P95 trop haut pendant SOUTENU_S secondes
        if p95 is not None and p95 > SEUIL_P95_MS:
            if self.p95_haut_depuis is None:
                self.p95_haut_depuis = t
            elif t - self.p95_haut_depuis >= SOUTENU_S:
                return self._fin(f"P95 > {SEUIL_P95_MS} ms pendant {SOUTENU_S} s", t, utilisateurs, p95)
        else:
            self.p95_haut_depuis = None

        # 2) Vague d'erreurs : SEUIL_ERREURS nouvelles erreurs en 10 s
        self.erreurs.append((t, stats.num_failures))
        self.erreurs = [(x, n) for x, n in self.erreurs if t - x <= 10]
        if stats.num_failures - self.erreurs[0][1] >= SEUIL_ERREURS:
            return self._fin(f"{SEUIL_ERREURS} erreurs ou plus en 10 s", t, utilisateurs, p95)

        # 3) Plafond atteint et tenu un palier entier : pas de rupture
        if t >= (MAX_UTILISATEURS // PAS_UTILISATEURS + 1) * PAS_DUREE_S:
            return self._fin("aucune rupture jusqu'à la limite fixée", t, MAX_UTILISATEURS, p95)

        return utilisateurs, PAS_UTILISATEURS
