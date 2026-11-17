"""TP2, étape 3 : défense contre l'attaque par évasion (normaliser_anti_evasion, api/preprocess.py).

Réexécute l'attaque du § 2 (attack/evasion.py) sur le même échantillon, avec et sans la
défense, pour mesurer son effet : précision, rappel, taux d'évasion, faux positifs, latence.

Lancement (depuis la racine) :
    .venv/bin/python -m attack.defense                     # DistilBERT, 500 + 500
Sorties : attack/results/defense_<modele>.json, .csv et .png
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from api import modeles
from api.preprocess import anonymiser, clean_text, pretraiter
from attack.evasion import ATTAQUES, SORTIES, attaquer, charger_echantillon, metriques, predire


def sans_defense(texte: str) -> str:
    """Même chaîne que l'API, mais SANS la défense anti-évasion (pour mesurer sa contribution)."""
    return clean_text(anonymiser(texte))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modele", default="distilbert", choices=["distilbert", "bilstm"])
    ap.add_argument("--n", type=int, default=500)
    args = ap.parse_args()

    modele = modeles.obtenir(args.modele)
    seuils = modeles.seuils(modele)
    modele.probabilites(pretraiter("warm up"))
    df = charger_echantillon(args.n)
    y = df.toxique.to_numpy()
    print(f"{len(df)} commentaires ({args.n} toxiques), modèle {args.modele}")

    variantes = {"sans attaque": df.comment_text.tolist()}
    for nom, f in ATTAQUES.items():
        variantes[nom] = [attaquer(t, f) for t in df.comment_text]

    resultats = {}
    for nom, textes in variantes.items():
        pred_sans, lat_sans = predire(modele, seuils, textes, pretraitement=sans_defense)
        pred_avec, lat_avec = predire(modele, seuils, textes, pretraitement=pretraiter)
        m_sans = metriques(y, pred_sans, lat_sans)
        m_avec = metriques(y, pred_avec, lat_avec)
        resultats[nom] = {"sans_defense": m_sans, "avec_defense": m_avec}
        print(f"{nom:14s} | rappel sans défense {m_sans['rappel']:.2f} -> avec défense {m_avec['rappel']:.2f} "
              f"| faux+ {m_sans['taux_faux_positifs']:.3f} -> {m_avec['taux_faux_positifs']:.3f}")

    # Taux d'évasion : parmi les toxiques détectés SANS attaque (avec défense active), combien
    # échappent encore UNE FOIS DÉGUISÉS, toujours avec la défense active.
    pred_ref, _ = predire(modele, seuils, variantes["sans attaque"], pretraitement=pretraiter)
    for nom, textes in variantes.items():
        if nom == "sans attaque":
            continue
        pred_avec, _ = predire(modele, seuils, textes, pretraitement=pretraiter)
        detectes = (pred_ref == 1) & (y == 1)
        resultats[nom]["avec_defense"]["taux_evasion"] = (
            round(float((pred_avec[detectes] == 0).mean()), 4) if detectes.any() else 0.0)

    SORTIES.mkdir(exist_ok=True)
    base = SORTIES / f"defense_{args.modele}"
    base.with_suffix(".json").write_text(json.dumps(resultats, indent=1, ensure_ascii=False), encoding="utf-8")
    lignes = []
    for nom, r in resultats.items():
        for cond in ("sans_defense", "avec_defense"):
            lignes.append({"attaque": nom, "condition": cond, **r[cond]})
    pd.DataFrame(lignes).to_csv(base.with_suffix(".csv"), index=False)
    graphique_defense(resultats, f"Effet de la défense anti-évasion : {args.modele} ({args.n}+{args.n} commentaires)",
                      base.with_suffix(".png"))
    print("écrit :", base.with_suffix(".json"), base.with_suffix(".csv"), base.with_suffix(".png"))


def graphique_defense(resultats: dict, titre: str, chemin: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    noms = list(resultats)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    x = np.arange(len(noms)); w = 0.35
    rappel_sans = [resultats[n]["sans_defense"]["rappel"] for n in noms]
    rappel_avec = [resultats[n]["avec_defense"]["rappel"] for n in noms]
    b1 = ax.bar(x - w/2, rappel_sans, w, label="Sans défense", color="#c0392b")
    b2 = ax.bar(x + w/2, rappel_avec, w, label="Avec défense", color="#1a7a4a")
    ax.bar_label(b1, fmt="%.2f", fontsize=8, padding=2)
    ax.bar_label(b2, fmt="%.2f", fontsize=8, padding=2)
    ax.set_xticks(x, noms, fontsize=9); ax.set_ylim(0, 1.15)
    ax.set_ylabel("Rappel"); ax.legend(fontsize=9)
    ax.set_title(titre, fontsize=11, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(chemin, dpi=140); plt.close(fig)


if __name__ == "__main__":
    main()
