"""Score les 20 phrases (attack/inter_equipes/phrases.csv) avec le modèle LOCAL, en version originale
et déguisée (combo), pour alimenter le dashboard. Pas d'appel réseau, pas de clé.

Usage : .venv/bin/python -m attack.inter_equipes.demo_local
Sortie : attack/results/demo_20.json
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from api_locale import modeles
from api_locale.preprocess import pretraiter

RACINE = Path(__file__).resolve().parent.parent.parent
SORTIE = Path(__file__).resolve().parent / "resultats" / "demo_20.json"

HOMOGLYPHES = {"a": "а", "e": "е", "o": "о", "i": "і", "c": "с", "p": "р", "y": "у", "x": "х"}
LEET = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "$", "t": "7"}
ZW = "​"


def piéger(texte: str) -> str:
    """Déguisement combiné (leet léger + homoglyphes + caractères invisibles) sur les mots longs,
    comme le ferait un humain qui veut passer la modération. Lisible à l'œil, cassé pour le modèle."""
    import random
    r = random.Random(42)
    t = "".join(LEET.get(c.lower(), c) if c.lower() in LEET and r.random() < 0.4 else c for c in texte)
    t = "".join(HOMOGLYPHES.get(c.lower(), c) if c.lower() in HOMOGLYPHES and r.random() < 0.7 else c for c in t)
    return " ".join(ZW.join(m) if len(m) > 3 else m for m in t.split())


def verdict(modele, seuils, texte):
    s = np.array([seuils[l] for l in modeles.LABELS])
    t0 = time.perf_counter()
    p = modele.probabilites(pretraiter(texte))
    latence = 1000 * (time.perf_counter() - t0)
    score = int(round(100 * float(p[0])))                 # score = proba toxic x 100 (comme l'API déployée)
    detecte = bool((p >= s).any())
    return score, detecte, round(latence, 1)


def main():
    modele = modeles.obtenir("distilbert")
    seuils = modeles.seuils(modele)
    modele.probabilites(pretraiter("warm up"))            # 1re inférence lente, hors mesure
    df = pd.read_csv(Path(__file__).resolve().parent / "phrases.csv")

    lignes = []
    for _, r in df.iterrows():
        pietege = piéger(r.text) if r.toxic == 1 else r.text
        s0, d0, l0 = verdict(modele, seuils, r.text)
        s1, d1, l1 = verdict(modele, seuils, pietege)
        lignes.append({
            "texte": r.text, "toxique_reel": int(r.toxic),
            "original": {"texte": r.text, "score": s0, "detecte": d0, "latence_ms": l0},
            "piege": {"texte": pietege, "score": s1, "detecte": d1, "latence_ms": l1},
            "evasion": bool(r.toxic == 1 and d0 and not d1),   # toxique vu avant, plus vu après
        })

    tox = [x for x in lignes if x["toxique_reel"] == 1]
    detect_avant = sum(x["original"]["detecte"] for x in tox)
    detect_apres = sum(x["piege"]["detecte"] for x in tox)
    resume = {
        "n_total": len(lignes), "n_toxiques": len(tox),
        "rappel_avant": round(detect_avant / len(tox), 3),
        "rappel_apres": round(detect_apres / len(tox), 3),
        "evasions": sum(x["evasion"] for x in lignes),
        "latence_moyenne_ms": round(np.mean([x["piege"]["latence_ms"] for x in lignes]), 1),
    }
    SORTIE.parent.mkdir(exist_ok=True)
    SORTIE.write_text(json.dumps({"resume": resume, "phrases": lignes}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resume, indent=1, ensure_ascii=False))
    print("écrit :", SORTIE)


if __name__ == "__main__":
    main()
