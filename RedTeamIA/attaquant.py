"""Générateur de charge du Red Team interne (vagues 7 et 8).

Bibliothèque standard seulement : le même fichier tourne sur un poste ET dans un pod du cluster (deuxième adresse
d'attaque). Chaque fil garde une connexion HTTPS ouverte (comme un outil de charge) et vise un débit total `debit`.

    URL=https://<adresse> API_KEY=... python attaquant.py --debit 180 --concurrence 128 --duree 120 [--sans-cle]

Résumé JSON sur la dernière ligne de la sortie. Garde-fous (kill switch), comme l'outil du professeur :
- arrêt si plus de 20 % d'erreurs serveur (5xx ou connexion perdue) sur les 10 dernières secondes ;
- arrêt si le P95 des 10 dernières secondes dépasse 10 s ;
- plafond absolu de requêtes (100 000) et de durée ;
- arrêt demandé de l'extérieur : fichier `--fichier-arret` (pod) ou événement (appel depuis un autre script).
"""
import argparse
import http.client
import json
import os
import ssl
import sys
import threading
import time

TEXTES = [  # textes courts et variés : une requête = un jeton de la limite de débit
    "Thanks for the update, the article is much clearer now", "You are a stupid idiot",
    "I disagree with this edit, please check the sources", "This page is garbage and so are you",
    "Can someone fix the broken link in the references?", "Great work on the history section",
    "Nobody cares about your opinion, loser", "The infobox should list the population in 2010",
]
PLAFOND_REQUETES = 100_000
FENETRE_S = 10


class Journal:
    """Enregistre (instant, code, durée) de chaque requête, protégé par un verrou (plusieurs fils écrivent)."""

    def __init__(self):
        self.verrou = threading.Lock()
        self.lignes: list[tuple[float, int, float]] = []

    def ajouter(self, t, code, duree):
        with self.verrou:
            self.lignes.append((t, code, duree))

    def recentes(self, depuis):
        with self.verrou:
            return [l for l in self.lignes if l[0] >= depuis]


def p95(valeurs):
    v = sorted(valeurs)
    return v[int(0.95 * (len(v) - 1))] if v else 0.0


def lancer(debit: float, concurrence: int, duree: float, avec_cle: bool = True, route: str = "/score",
           arret: threading.Event | None = None, fichier_arret: str | None = None, chaque_seconde=None) -> dict:
    """`chaque_seconde(bilan)` est appelé une fois par seconde avec les réponses de la seconde écoulée (tableau de bord)."""
    url, cle = os.environ["URL"].rstrip("/"), os.environ.get("API_KEY", "")
    hote = url.split("//", 1)[1]
    arret = arret or threading.Event()
    raison = {"valeur": "durée atteinte"}
    journal = Journal()
    ctx = ssl.create_default_context()
    entetes = {"Content-Type": "application/json", "User-Agent": "redteam-interne-dss/1.0"}
    if avec_cle:
        entetes["X-API-Key"] = cle
    t0 = time.monotonic()
    fin = t0 + duree
    intervalle = concurrence / debit      # chaque fil envoie une requête toutes les `intervalle` secondes

    def fil(i):
        conn, prochain = None, t0 + (i / concurrence) * intervalle
        k = i
        while not arret.is_set() and time.monotonic() < fin:
            attente = prochain - time.monotonic()
            if attente > 0:
                time.sleep(min(attente, 0.5))
                continue
            prochain = max(prochain + intervalle, time.monotonic() - 1)   # en retard : pas de rattrapage en rafale
            corps = json.dumps({"text": TEXTES[k % len(TEXTES)]})
            k += 1
            debut = time.monotonic()
            try:
                if conn is None:
                    conn = http.client.HTTPSConnection(hote, timeout=15, context=ctx)
                conn.request("POST", route, body=corps, headers=entetes)
                rep = conn.getresponse()
                rep.read()
                code = rep.status
                if (rep.getheader("connection") or "").lower() == "close":
                    conn.close()
                    conn = None
            except Exception:       # délai dépassé, connexion coupée... : compté comme erreur (code 0)
                code = 0
                if conn is not None:
                    conn.close()
                conn = None
            journal.ajouter(time.monotonic() - t0, code, time.monotonic() - debut)
        if conn is not None:
            conn.close()

    def surveiller():
        while not arret.is_set() and time.monotonic() < fin:
            time.sleep(1)
            if chaque_seconde:
                maintenant = time.monotonic() - t0
                derniere = journal.recentes(maintenant - 1)
                codes_s = {}
                for _, c, _ in derniere:
                    codes_s[str(c)] = codes_s.get(str(c), 0) + 1
                ok_s = [d for _, c, d in derniere if c == 200]
                chaque_seconde({"seconde": int(maintenant), "codes": codes_s, "total": len(journal.lignes),
                                "p95_200_ms": round(1000 * p95(ok_s)) if ok_s else None})
            if fichier_arret and os.path.exists(fichier_arret):
                raison["valeur"] = "arrêt demandé"
                arret.set()
            recent = journal.recentes(time.monotonic() - t0 - FENETRE_S)
            if len(journal.lignes) >= PLAFOND_REQUETES:
                raison["valeur"] = "plafond de requêtes"
                arret.set()
            if len(recent) >= 20:
                erreurs = sum(1 for _, c, _ in recent if c == 0 or c >= 500 and c != 503)
                if erreurs / len(recent) > 0.2:
                    raison["valeur"] = f"kill switch : {erreurs}/{len(recent)} erreurs serveur en {FENETRE_S} s"
                    arret.set()
                if p95([d for _, _, d in recent]) > 10:
                    raison["valeur"] = f"kill switch : P95 > 10 s sur {FENETRE_S} s"
                    arret.set()
        if arret.is_set() and raison["valeur"] == "durée atteinte":
            raison["valeur"] = "arrêt demandé"

    fils = [threading.Thread(target=fil, args=(i,), daemon=True) for i in range(concurrence)]
    garde = threading.Thread(target=surveiller, daemon=True)
    for f in fils:
        f.start()
    garde.start()
    for f in fils:
        f.join()
    arret.set()
    ecoule = time.monotonic() - t0
    lignes = journal.lignes
    codes = {}
    for _, c, _ in lignes:
        codes[str(c)] = codes.get(str(c), 0) + 1
    par_seconde = {}
    for t, c, _ in lignes:
        s = par_seconde.setdefault(int(t), {})
        s[str(c)] = s.get(str(c), 0) + 1
    ok = [d for _, c, d in lignes if c == 200]
    return {"debit_vise": debit, "concurrence": concurrence, "duree_s": round(ecoule, 1), "avec_cle": avec_cle,
            "route": route, "requetes": len(lignes), "debit_obtenu": round(len(lignes) / ecoule, 1), "codes": codes,
            "acceptees_200": len(ok), "latence_200_p50_ms": round(1000 * sorted(ok)[len(ok) // 2]) if ok else None,
            "latence_200_p95_ms": round(1000 * p95(ok)) if ok else None, "arret": raison["valeur"],
            "par_seconde": par_seconde}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debit", type=float, default=180)
    ap.add_argument("--concurrence", type=int, default=128)
    ap.add_argument("--duree", type=float, default=120)
    ap.add_argument("--sans-cle", action="store_true")
    ap.add_argument("--route", default="/score")
    ap.add_argument("--attendre-fichier", help="ne démarre qu'à l'apparition de ce fichier (synchronisation)")
    ap.add_argument("--fichier-arret")
    ap.add_argument("--flux", action="store_true", help="une ligne « @@SEC {json} » par seconde (suivi en direct)")
    a = ap.parse_args()
    if a.attendre_fichier:
        while not os.path.exists(a.attendre_fichier):
            time.sleep(0.2)
    rapporter = (lambda b: print("@@SEC " + json.dumps(b), flush=True)) if a.flux else None
    res = lancer(a.debit, a.concurrence, a.duree, not a.sans_cle, a.route, fichier_arret=a.fichier_arret,
                 chaque_seconde=rapporter)
    sys.stdout.write(json.dumps(res) + "\n")


if __name__ == "__main__":
    main()
