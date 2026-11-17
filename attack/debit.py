"""TP2, étape 3 : mesure l'effet du limiteur de débit (api/limiteur_debit.py) contre le vol
de modèle, en rejouant l'attaque en vrai HTTP contre l'API locale en cours d'exécution.

Lancement (l'API doit déjà tourner, voir le README du script) :
    .venv/bin/python -m attack.debit --duree 30
"""
import argparse
import time

import requests


def rafale(url: str, duree_s: float):
    """Envoie des requêtes aussi vite que possible pendant `duree_s` secondes. Renvoie
    (nb_200, nb_429, nb_autres, requetes_par_s_effectif)."""
    t0 = time.monotonic()
    n200 = n429 = nautres = 0      # réponses exploitables / refusées par le limiteur / autres (erreurs réseau comprises)
    with requests.Session() as s:      # une session réutilise la connexion : on mesure le limiteur, pas l'ouverture de connexions
        while time.monotonic() - t0 < duree_s:
            try:
                r = s.post(f"{url}/predire", json={"texte": "You are a stupid idiot"}, timeout=5)
                if r.status_code == 200:      # le modèle a répondu : l'attaquant obtient une réponse utilisable
                    n200 += 1
                elif r.status_code == 429:      # refusé par le limiteur avant d'atteindre le modèle
                    n429 += 1
                else:
                    nautres += 1
            except requests.RequestException:
                nautres += 1
    ecoule = time.monotonic() - t0
    return n200, n429, nautres, round((n200 + n429 + nautres) / ecoule, 1)


def main():
    # Cible par défaut : l'API LOCALE (route /predire). On n'attaque jamais l'API déployée avec ce script.
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--duree", type=float, default=30)
    args = ap.parse_args()

    print(f"Rafale de requêtes pendant {args.duree} s contre {args.url} (Ctrl+C pour arrêter)...")
    n200, n429, nautres, debit = rafale(args.url, args.duree)
    print(f"200 OK : {n200}  |  429 rejetées : {n429}  |  autres erreurs : {nautres}  |  {debit} req/s tentées")
    if n429 == 0:
        print(f"-> aucun rejet : l'attaquant a obtenu {n200} réponses exploitables en {args.duree:.0f} s.")
    else:
        print(f"-> le limiteur a bloqué l'attaquant : seulement {n200} réponses exploitables obtenues, "
              f"le reste ({n429}) rejeté en 429 avant même d'atteindre le modèle.")


if __name__ == "__main__":
    main()
