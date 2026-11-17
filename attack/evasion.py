"""TP2, étape 2 : attaque par évasion sur le modèle de toxicité.

L'attaquant déguise les mots toxiques (leetspeak, lettres espacées, homoglyphes, caractères invisibles)
pour que le modèle ne les reconnaisse plus. Le script mesure, avant et après l'attaque :
précision, rappel, taux de faux positifs, F1, taux d'évasion et latence.

Lancement (depuis la racine) :
    .venv/bin/python -m attack.evasion                     # DistilBERT, 500 toxiques + 500 non toxiques
    .venv/bin/python -m attack.evasion --modele bilstm --n 300
Sorties : attack/results/evasion_<modele>.json, .csv et .png
"""
import argparse
import json
import random
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

from api_locale import modeles
from api_locale.preprocess import _est_toxique, pretraiter

RACINE = Path(__file__).resolve().parent.parent
SORTIES = Path(__file__).resolve().parent / "results"
SEED = 42

# Les trois tables ci-dessous sont les déguisements que ferait un humain pour qu'un mot reste lisible mais change d'aspect.
LEET = {"a": "@", "e": "3", "i": "1", "o": "0", "s": "$", "t": "7"}
HOMOGLYPHES = {"a": "а", "e": "е", "o": "о", "c": "с", "p": "р", "x": "х", "i": "і", "y": "у"}   # cyrillique
INVISIBLE = "​"   # espace sans chasse


def leet(mot: str) -> str:
    """idiot -> 1d10t : lettres remplacées par des chiffres ou symboles ressemblants."""
    return "".join(LEET.get(c.lower(), c) for c in mot)


def espaces(mot: str) -> str:
    """idiot -> i d i o t : une espace entre chaque lettre."""
    return " ".join(mot)


def homoglyphes(mot: str) -> str:
    """idiot -> іdіоt : lettres latines remplacées par des lettres cyrilliques identiques à l'œil."""
    return "".join(HOMOGLYPHES.get(c, c) for c in mot)


def invisibles(mot: str) -> str:
    """Insère un espace sans chasse (U+200B), invisible à l'écran, entre chaque lettre : le mot reste lisible pour un humain."""
    return INVISIBLE.join(mot)


ATTAQUES = {"leetspeak": leet, "espaces": espaces, "homoglyphes": homoglyphes, "invisibles": invisibles}


def attaquer(texte: str, transformation, rng: random.Random | None = None) -> str:
    """Applique la transformation aux seuls mots toxiques : le reste du texte est intact, comme le ferait un humain."""
    def remplacer(m):
        mot = m.group()
        if not _est_toxique(mot.lower()):      # mot ordinaire : laissé tel quel
            return mot
        # Avec `rng` (variante « mélange »), chaque mot toxique reçoit un déguisement tiré au hasard
        f = transformation if rng is None else rng.choice(list(ATTAQUES.values()))
        return f(mot)
    return re.sub(r"[A-Za-z]+", remplacer, texte)


def charger_echantillon(n: int) -> pd.DataFrame:
    """n commentaires toxiques + n non toxiques du test officiel (lignes à -1 exclues), graine fixe."""
    textes = pd.read_csv(RACINE / "data" / "test.csv")
    labels = pd.read_csv(RACINE / "data" / "test_labels.csv")
    df = textes.merge(labels, on="id")
    df = df[df[modeles.LABELS].ne(-1).all(axis=1)].copy()
    df["toxique"] = df[modeles.LABELS].max(axis=1).astype(int)      # toxique = au moins un des 6 labels vaut 1
    # on ne garde que les toxiques qui contiennent au moins un mot de la liste : sinon l'attaque n'a rien à déguiser
    contient = df["comment_text"].str.lower().str.findall(r"[a-z]+").apply(lambda ms: any(_est_toxique(m) for m in ms))
    tox = df[(df.toxique == 1) & contient].sample(n, random_state=SEED)      # graine fixe : échantillon reproductible
    sain = df[df.toxique == 0].sample(n, random_state=SEED)
    return pd.concat([tox, sain]).reset_index(drop=True)


def predire(modele, seuils: dict, textes, pretraitement=pretraiter):
    """Pour chaque texte : toxique prédit (au moins un label au-dessus de son seuil) et latence (ms)."""
    s = np.array([seuils[l] for l in modeles.LABELS])
    preds, latences = [], []
    for t in textes:
        t0 = time.perf_counter()
        p = modele.probabilites(pretraitement(t))
        latences.append(1000 * (time.perf_counter() - t0))
        preds.append(int((p >= s).any()))      # toxique prédit si AU MOINS UN label dépasse son seuil
    return np.array(preds), np.array(latences)


def metriques(y, pred, latences, pred_reference=None) -> dict:
    # vp/fp/fn/vn : vrais positifs, faux positifs, faux négatifs, vrais négatifs
    vp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum()); vn = int(((pred == 0) & (y == 0)).sum())
    precision = vp / (vp + fp) if vp + fp else 0.0
    rappel = vp / (vp + fn) if vp + fn else 0.0
    m = {"precision": precision, "rappel": rappel,
         "taux_faux_positifs": fp / (fp + vn) if fp + vn else 0.0,
         "f1": 2 * precision * rappel / (precision + rappel) if precision + rappel else 0.0,
         "exactitude": (vp + vn) / len(y),
         "latence_moyenne_ms": float(latences.mean()), "latence_p95_ms": float(np.percentile(latences, 95))}
    if pred_reference is not None:   # toxiques détectés sans attaque, qui ne le sont plus avec
        detectes = (pred_reference == 1) & (y == 1)
        m["taux_evasion"] = float((pred[detectes] == 0).mean()) if detectes.any() else 0.0
    return {k: round(v, 4) for k, v in m.items()}


def graphique(resultats: dict, titre: str, chemin: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    noms = list(resultats)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.8), gridspec_kw={"width_ratios": [3, 1.2]})
    cles = [("precision", "Précision"), ("rappel", "Rappel"), ("taux_faux_positifs", "Faux positifs"), ("taux_evasion", "Évasion")]
    couleurs = ["#2a6db5", "#1a7a4a", "#c0392b", "#d4680a"]
    x = np.arange(len(noms)); w = 0.2
    for i, ((cle, lib), c) in enumerate(zip(cles, couleurs)):
        vals = [resultats[n].get(cle, 0) for n in noms]
        barres = a1.bar(x + (i - 1.5) * w, vals, w, label=lib, color=c)
        a1.bar_label(barres, fmt="%.2f", fontsize=7, padding=1)
    a1.set_xticks(x, noms, fontsize=9); a1.set_ylim(0, 1.1); a1.legend(fontsize=8, ncol=4, loc="upper right")
    a1.set_title("Qualité de détection", fontsize=10); a1.spines[["top", "right"]].set_visible(False)
    lat = [resultats[n]["latence_moyenne_ms"] for n in noms]
    barres = a2.barh(noms, lat, color="#888880"); a2.bar_label(barres, fmt="%.1f ms", fontsize=8, padding=2)
    a2.invert_yaxis(); a2.set_title("Latence moyenne par commentaire", fontsize=10)
    a2.spines[["top", "right"]].set_visible(False); a2.set_xlim(0, max(lat) * 1.35)
    fig.suptitle(titre, fontsize=12, fontweight="bold")
    fig.tight_layout(); fig.savefig(chemin, dpi=140); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modele", default="distilbert", choices=["distilbert", "bilstm"])
    ap.add_argument("--n", type=int, default=500, help="nombre de commentaires toxiques (et autant de non toxiques)")
    args = ap.parse_args()

    modele = modeles.obtenir(args.modele)
    seuils = modeles.seuils(modele)
    modele.probabilites(pretraiter("warm up"))   # la 1re inférence est lente : elle fausserait la latence
    df = charger_echantillon(args.n)
    y = df.toxique.to_numpy()
    print(f"{len(df)} commentaires ({args.n} toxiques), modèle {args.modele}, seuils {seuils}")

    variantes = {"sans attaque": df.comment_text.tolist()}
    for nom, f in ATTAQUES.items():
        variantes[nom] = [attaquer(t, f) for t in df.comment_text]
    rng = random.Random(SEED)
    variantes["mélange"] = [attaquer(t, None, rng) for t in df.comment_text]

    resultats, reference = {}, None      # reference = verdicts SANS attaque, pour calculer le taux d'évasion
    for nom, textes in variantes.items():
        pred, lat = predire(modele, seuils, textes)
        if reference is None:
            reference = pred
        resultats[nom] = metriques(y, pred, lat, reference)
        print(f"{nom:14s} {resultats[nom]}")

    exemple = df[df.toxique == 1].comment_text.iloc[0][:120]
    SORTIES.mkdir(exist_ok=True)
    base = SORTIES / f"evasion_{args.modele}"
    base.with_suffix(".json").write_text(json.dumps(
        {"modele": args.modele, "n_toxiques": args.n, "n_non_toxiques": args.n, "seuils": seuils,
         "exemples": {nom: attaquer(exemple, f) for nom, f in ATTAQUES.items()}, "resultats": resultats},
        ensure_ascii=False, indent=1), encoding="utf-8")
    pd.DataFrame(resultats).T.to_csv(base.with_suffix(".csv"))
    graphique(resultats, f"Attaque par évasion : {args.modele} ({args.n} toxiques + {args.n} non toxiques)",
              base.with_suffix(".png"))
    print("écrit :", base.with_suffix(".json"), base.with_suffix(".csv"), base.with_suffix(".png"))


if __name__ == "__main__":
    main()
