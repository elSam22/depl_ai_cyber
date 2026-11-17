"""Vague 5 : vol de modèle (extraction) par requêtes rapides.

Reproduit la sonde du professeur : chez une autre équipe, « 400 échantillons en 12 s (2 005 requêtes/min, zéro 429) » ;
chez une autre, « 30 échantillons puis 429 en masse (489/min) ». L'attaquant envoie des commentaires variés avec la clé,
le plus vite possible (16 requêtes en parallèle), et garde chaque réponse 200 comme exemple d'entraînement d'un clone.
Mesure : nombre de réponses exploitables, délai avant le premier 429, réponses exploitables par minute.
"""
import concurrent.futures as cf
import time

import pandas as pd

from commun import CLE, RACINE, URL, ecrire, evenement, verifier_cible

import httpx

N = 400
PARALLELE = 16


def main():
    verifier_cible()
    textes = pd.read_csv(RACINE / "data" / "test.csv")["comment_text"].astype(str).sample(N, random_state=7)
    textes = [t[:1500] for t in textes]       # textes courts ou moyens : comme un attaquant pressé
    journal = []
    t0 = time.monotonic()

    def envoyer(texte):
        with httpx.Client(timeout=30) as c:
            debut = time.monotonic() - t0
            try:
                code = c.post(URL + "/score", json={"text": texte}, headers={"X-API-Key": CLE}).status_code
            except httpx.HTTPError:
                code = 0
            evenement("extraction", code=code, t_rel=round(time.monotonic() - t0, 2))
            return debut, code

    with cf.ThreadPoolExecutor(PARALLELE) as ex:
        journal = sorted(ex.map(envoyer, textes))
    duree = time.monotonic() - t0
    codes = [c for _, c in journal]
    ok = codes.count(200)
    premier_429 = next((round(t, 1) for t, c in journal if c == 429), None)
    ok_avant_429 = sum(1 for t, c in journal if c == 200 and (premier_429 is None or t < premier_429))
    resultat = {
        "requetes": N, "duree_s": round(duree, 1), "debit_tente_par_min": round(N / duree * 60),
        "reponses_exploitables": ok, "exploitables_par_min": round(ok / duree * 60),
        "codes": {str(c): codes.count(c) for c in sorted(set(codes))},
        "premier_429_apres_s": premier_429, "exploitables_avant_premier_429": ok_avant_429,
        "reference_professeur": {"sans_limite": "400 en 12 s, 2 005/min, 0 × 429",
                                 "limite_partielle": "30 puis 429 en masse, 489/min"},
    }
    resultat["verdict"] = ("freiné" if ok < N * 0.5 else "NON freiné")
    ecrire("v5_extraction", resultat)
    print(f"   {ok}/{N} réponses exploitables en {duree:.0f} s ({resultat['exploitables_par_min']}/min), "
          f"premier 429 à {premier_429} s, codes {resultat['codes']}")


if __name__ == "__main__":
    main()
