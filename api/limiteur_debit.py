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
        # Pour chaque identifiant (adresse IP) : la file des instants de ses requêtes récentes, du plus ancien au plus récent.
        self._historique: dict[str, deque] = defaultdict(deque)
        # L'API traite plusieurs requêtes à la fois (fils d'exécution) : le verrou évite que deux d'entre elles modifient
        # la même file en même temps et faussent le compte.
        self._verrou = Lock()

    def _nettoyer(self, h: deque, maintenant: float) -> None:
        # Les plus anciens instants sont à gauche : on retire ceux qui sont sortis de la fenêtre.
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
        maintenant = time.monotonic()      # horloge monotone : insensible à un changement d'heure du système
        with self._verrou:
            self._purger(maintenant)
            h = self._historique[cle]
            self._nettoyer(h, maintenant)
            if len(h) >= self.max_requetes:
                # Refus (non compté dans l'historique) : le client pourra réessayer quand la plus ancienne requête
                # de la fenêtre en sortira.
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
            h = self._historique.get(cle)      # .get et non [] : une simple lecture ne doit pas créer d'entrée
            if not h:
                return False, 0.0
            self._nettoyer(h, maintenant)
            if len(h) >= self.max_requetes:
                return True, round(self.fenetre_s - (maintenant - h[0]), 1)
            return False, 0.0


class SeauJetons:
    """Débit lissé (« throttling progressif ») : chaque identifiant a un seau de `capacite` jetons qui se remplit de
    `debit_par_s` jetons par seconde ; une requête consomme un jeton. Une petite rafale est permise, puis le client
    est ramené au débit moyen. Différence avec la fenêtre glissante : 60 requêtes/minute en fenêtre peuvent arriver
    toutes dans la même seconde et occuper tous les calculs du pod ; avec le seau, au plus `capacite` d'un coup."""

    def __init__(self, capacite: int, debit_par_s: float):
        self.capacite = capacite
        self.debit_par_s = debit_par_s
        # identifiant -> (jetons restants, instant de la dernière mise à jour). Le seau n'est pas rempli par un minuteur :
        # on calcule les jetons gagnés depuis la dernière visite, au moment où le client revient.
        self._seaux: dict[str, tuple[float, float]] = {}
        self._verrou = Lock()

    def autoriser(self, cle: str, cout: float = 1) -> tuple[bool, float]:
        """Consomme `cout` jetons (plafonné à la capacité : une requête maximale reste possible, seau plein)."""
        cout = min(cout, self.capacite)
        maintenant = time.monotonic()
        with self._verrou:
            if len(self._seaux) >= SEUIL_PURGE:      # seaux pleins depuis longtemps : inutiles
                self._seaux = {k: v for k, v in self._seaux.items()
                               if v[0] + (maintenant - v[1]) * self.debit_par_s < self.capacite}
            # Un nouveau client commence avec un seau plein (il peut faire une rafale tout de suite).
            jetons, avant = self._seaux.get(cle, (float(self.capacite), maintenant))
            jetons = min(self.capacite, jetons + (maintenant - avant) * self.debit_par_s)    # remplissage, plafonné
            if jetons < cout:
                self._seaux[cle] = (jetons, maintenant)
                # Attente = temps nécessaire pour regagner les jetons qui manquent.
                return False, round((cout - jetons) / self.debit_par_s, 1)
            self._seaux[cle] = (jetons - cout, maintenant)
            return True, 0.0


class Sanctions:
    """Sanction progressive : un client qui continue d'envoyer après `seuil_refus` refus en `fenetre_s` secondes est
    bloqué 30 s, puis 60, 120... jusqu'à `max_s`. La sanction est oubliée après `oubli_s` secondes de calme. Un client
    bloqué est refusé avant tout autre contrôle : un flot continu coûte de moins en moins cher au serveur."""

    def __init__(self, seuil_refus: int = 20, fenetre_s: float = 60, base_s: float = 30, max_s: float = 900,
                 oubli_s: float = 900):
        self.refus = LimiteurDebit(seuil_refus, fenetre_s)
        self.base_s, self.max_s, self.oubli_s = base_s, max_s, oubli_s
        # identifiant -> (niveau de sanction, fin du blocage en cours). Le niveau monte à chaque récidive : 30 s, 60 s, 120 s...
        self._etat: dict[str, tuple[int, float]] = {}
        self._verrou = Lock()

    def bloque(self, cle: str) -> tuple[bool, float]:
        """Renvoie (bloqué, secondes_restantes) : le client est-il actuellement sous sanction ?"""
        with self._verrou:
            niveau, fin = self._etat.get(cle, (0, 0.0))
            reste = fin - time.monotonic()
            return (True, round(reste, 1)) if reste > 0 else (False, 0.0)

    def enregistrer_refus(self, cle: str) -> float:
        """Compte un refus ; renvoie la durée du blocage s'il en déclenche un, sinon 0."""
        self.refus.enregistrer(cle)
        if not self.refus.bloque(cle)[0]:      # pas encore `seuil_refus` refus dans la fenêtre : pas de sanction
            return 0.0
        maintenant = time.monotonic()
        with self._verrou:
            niveau, fin = self._etat.get(cle, (0, 0.0))
            if maintenant - fin > self.oubli_s:      # assez longtemps sans incident : on repart de zéro
                niveau = 0
            duree = min(self.base_s * 2 ** niveau, self.max_s)      # doublement à chaque récidive, plafonné
            self._etat[cle] = (niveau + 1, maintenant + duree)
            if len(self._etat) >= SEUIL_PURGE:
                self._etat = {k: v for k, v in self._etat.items() if maintenant - v[1] <= self.oubli_s}
        # Le compteur de refus repart de zéro : pendant le blocage les requêtes sont refusées d'office, elles ne doivent
        # pas déclencher aussitôt une nouvelle sanction à la fin du blocage.
        with self.refus._verrou:
            self.refus._historique.pop(cle, None)
        return duree
