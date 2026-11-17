"""TP2 : rejoue l'évasion (étape 2) et le noyage CONTRE L'API DÉPLOYÉE, avec ses défenses en service.

Même protocole que attack/evasion.py (mots toxiques seuls déguisés, test officiel, graine 42), mais par HTTP sur
`POST /score` : on mesure ce qu'un vrai attaquant obtient, réseau, prétraitement et limites de débit compris.
Les requêtes sont espacées pour rester sous la limite de débit (sinon on mesurerait nos propres refus 429).

À n'utiliser QUE contre notre API. L'adresse et la clé sont lues dans l'environnement, jamais écrites :
    URL=https://<domaine> API_KEY=... python -m attack.mesure_api_deployee [--n 60]
Sorties : attack/results/api_deployee.json et attack/results/api_deployee.png
"""
import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from attack.evasion import ATTAQUES, SEED, attaquer, charger_echantillon  # noqa: E402

SORTIES = Path(__file__).resolve().parent / "results"
URL, CLE = os.environ["URL"].rstrip("/"), os.environ["API_KEY"]
PAUSE_S = 0.7          # ≈ 1,4 requête/s : sous la limite de /score (rafale 10 puis 1/s par pod, 2 pods)


def scorer(texte: str) -> tuple[bool, float]:
    """Renvoie (toxique, latence en ms). Attend et réessaie si l'API répond 429 (limite de débit)."""
    corps = json.dumps({"text": texte[:5000]}).encode()
    while True:
        req = urllib.request.Request(URL + "/score", data=corps, method="POST",
                                     headers={"Content-Type": "application/json", "X-API-Key": CLE})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=30) as r:  # nosec B310 (adresse https de notre API)
                rep = json.load(r)
            time.sleep(PAUSE_S)
            return rep["toxique"], 1000 * (time.perf_counter() - t0)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                time.sleep(float(e.headers.get("Retry-After", "2")) + 0.5)
                continue
            raise


def metriques(y, pred, lat, ref=None) -> dict:
    vp = sum(1 for a, b in zip(y, pred) if a and b)
    fp = sum(1 for a, b in zip(y, pred) if not a and b)
    pos, neg = sum(y), len(y) - sum(y)
    m = {"precision": round(vp / max(vp + fp, 1), 3), "rappel": round(vp / max(pos, 1), 3),
         "taux_faux_positifs": round(fp / max(neg, 1), 3), "latence_mediane_ms": round(sorted(lat)[len(lat) // 2])}
    if ref is not None:   # évasion : toxiques détectés sans attaque qui ne le sont plus
        base = [i for i, (a, b) in enumerate(zip(y, ref)) if a and b]
        m["taux_evasion"] = round(sum(1 for i in base if not pred[i]) / max(len(base), 1), 3)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60, help="commentaires toxiques ET non toxiques")
    n = ap.parse_args().n
    df = charger_echantillon(n)
    y = df["toxique"].astype(bool).tolist()
    textes = df["comment_text"].astype(str).tolist()
    res = {}

    pred, lat = zip(*(scorer(t) for t in textes))
    res["sans attaque"] = metriques(y, pred, lat)
    reference = list(pred)
    print("sans attaque", res["sans attaque"], flush=True)
    for nom, f in ATTAQUES.items():
        pred, lat = zip(*(scorer(attaquer(t, f)) for t in textes))
        res[nom] = metriques(y, pred, lat, reference)
        print(nom, res[nom], flush=True)

    # Noyage : les toxiques précédés de 1 000 puis 3 000 caractères tirés de commentaires non toxiques
    rng = random.Random(SEED)
    neutres = df[~df["toxique"].astype(bool)]["comment_text"].astype(str).tolist()
    def rembourrage(k):
        s = ""
        while len(s) < k:
            s += rng.choice(neutres) + " "
        return s[:k]
    tox = [t for t, v in zip(textes, y) if v]
    detectes = [t for t, r in zip(tox, [p for p, v in zip(reference, y) if v]) if r]
    for k in (1000, 3000):
        p, lat = zip(*(scorer(rembourrage(k) + " " + t) for t in detectes))
        res[f"noyage {k} car."] = {"detectes": f"{sum(p)}/{len(detectes)}", "taux_evasion": round(1 - sum(p) / len(detectes), 3),
                                   "latence_mediane_ms": round(sorted(lat)[len(lat) // 2])}
        print(f"noyage {k}", res[f"noyage {k} car."], flush=True)

    SORTIES.mkdir(exist_ok=True)
    (SORTIES / "api_deployee.json").write_text(json.dumps({"n": n, "date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
                                                           "resultats": res}, ensure_ascii=False, indent=1))
    noms = [k for k in res if "noyage" not in k]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = range(len(noms))
    ax.bar([i - 0.2 for i in x], [res[k]["rappel"] for k in noms], 0.4, label="rappel", color="#2a78d6")
    ax.bar([i + 0.2 for i in x], [res[k]["precision"] for k in noms], 0.4, label="précision", color="#8ab6e8")
    for i, k in enumerate(noms):
        ax.text(i - 0.2, res[k]["rappel"] + 0.02, f"{res[k]['rappel']:.2f}", ha="center", fontsize=8)
    ax.set_xticks(list(x), noms); ax.set_ylim(0, 1.1); ax.legend(loc="lower right")
    ax.set_title(f"Évasion contre l'API DÉPLOYÉE, défenses en service ({n} toxiques + {n} sains, par HTTP)")
    fig.tight_layout(); fig.savefig(SORTIES / "api_deployee.png", dpi=130)


if __name__ == "__main__":
    main()
