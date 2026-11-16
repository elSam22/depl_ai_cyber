"""TP2, étape 3 : défense par limitation de débit contre le vol de modèle reçu sur notre API.

Le vol de modèle a marché parce qu'il n'y avait aucune limite au nombre de requêtes qu'un
client pouvait envoyer (voir attack/RAPPORT.md § 5 : 2000 requêtes, latence doublée, aucun
rejet). Cette limite-ci rejette (429) un client qui dépasse un quota de requêtes par fenêtre
de temps glissante, par identifiant (clé API en production ; IP en local, faute de clé).
"""
import time
from collections import defaultdict, deque
from threading import Lock


class LimiteurDebit:
    """Fenêtre glissante : au plus `max_requetes` requêtes par `fenetre_s` secondes, par clé."""

    def __init__(self, max_requetes: int, fenetre_s: float):
        self.max_requetes = max_requetes
        self.fenetre_s = fenetre_s
        self._historique: dict[str, deque] = defaultdict(deque)
        self._verrou = Lock()

    def autoriser(self, cle: str) -> tuple[bool, float]:
        """Renvoie (autorisé, secondes_avant_prochain_essai). Enregistre la requête si autorisée."""
        maintenant = time.monotonic()
        with self._verrou:
            h = self._historique[cle]
            while h and maintenant - h[0] > self.fenetre_s:
                h.popleft()
            if len(h) >= self.max_requetes:
                return False, round(self.fenetre_s - (maintenant - h[0]), 1)
            h.append(maintenant)
            return True, 0.0
