"""Limitation de débit par fenêtre glissante (défense contre le déni de service, le vol de modèle et le brute-force).

Écrit par Eliana pour le TP2 (étape 3) : le vol de modèle a marché parce qu'aucune limite ne bornait le nombre de
requêtes d'un client (attack/RAPPORT.md § 5 : 2000 requêtes, aucun rejet). Branché dans l'API par protection.py.
Ajouts : lecture sans enregistrement (`bloque`), enregistrement seul (`enregistrer`), purge de la mémoire.
"""
import time
from collections import defaultdict, deque
from threading import Lock

SEUIL_PURGE = 10_000      # nombre d'identifiants au-delà duquel on supprime ceux dont la fenêtre est vide


class LimiteurDebit:
    """Fenêtre glissante : au plus `max_requetes` requêtes par `fenetre_s` secondes, par identifiant."""

    def __init__(self, max_requetes: int, fenetre_s: float):
        self.max_requetes = max_requetes
        self.fenetre_s = fenetre_s
        self._historique: dict[str, deque] = defaultdict(deque)
        self._verrou = Lock()

    def _nettoyer(self, h: deque, maintenant: float) -> None:
        while h and maintenant - h[0] > self.fenetre_s:
            h.popleft()

    def _purger(self, maintenant: float) -> None:
        """Évite qu'un grand nombre d'adresses différentes remplisse la mémoire du pod."""
        if len(self._historique) < SEUIL_PURGE:
            return
        for cle in list(self._historique):
            self._nettoyer(self._historique[cle], maintenant)
            if not self._historique[cle]:
                del self._historique[cle]

    def autoriser(self, cle: str) -> tuple[bool, float]:
        """Renvoie (autorisé, secondes_avant_prochain_essai). Enregistre la requête si autorisée."""
        maintenant = time.monotonic()
        with self._verrou:
            self._purger(maintenant)
            h = self._historique[cle]
            self._nettoyer(h, maintenant)
            if len(h) >= self.max_requetes:
                return False, round(self.fenetre_s - (maintenant - h[0]), 1)
            h.append(maintenant)
            return True, 0.0

    def enregistrer(self, cle: str) -> None:
        """Compte un événement (par exemple une clé refusée) sans rien autoriser ni refuser."""
        maintenant = time.monotonic()
        with self._verrou:
            h = self._historique[cle]
            self._nettoyer(h, maintenant)
            h.append(maintenant)

    def bloque(self, cle: str) -> tuple[bool, float]:
        """Renvoie (bloqué, secondes_restantes) sans enregistrer de requête."""
        maintenant = time.monotonic()
        with self._verrou:
            h = self._historique.get(cle)
            if not h:
                return False, 0.0
            self._nettoyer(h, maintenant)
            if len(h) >= self.max_requetes:
                return True, round(self.fenetre_s - (maintenant - h[0]), 1)
            return False, 0.0
