"""TP2, étape 2 (incident reçu) + étape 3 : simulation de vol de modèle contre notre
propre modèle, pour mesurer l'effet de la défense (api/defense_extraction.quantifier_score).

Un attaquant externe a réellement fait ça contre notre API déployée (score exact à 1
décimale, probabilités à 4 décimales, aucune limite de débit observée) : voir
attack/RAPPORT.md § 5 pour le constat. Ce script le reproduit en local pour chiffrer
l'effet de la défense, comme demandé à l'étape 3 ("réexécutez l'attaque, mesurez avant/après").

Protocole : l'attaquant envoie N textes (sans leurs vrais labels) à notre modèle, récupère
les réponses (brutes ou quantifiées selon la condition), entraîne un clone (TF-IDF +
régression logistique, un par label) sur ces réponses, puis on mesure sur un jeu étiqueté
séparé : l'accord clone/cible, la précision du clone, ses faux positifs, et sa fidélité label
par label.

Lancement (depuis la racine) :
    .venv/bin/python -m attack.extraction                 # DistilBERT, N dans [100,500,1000,2000]
Sorties : attack/results/extraction.json, .csv et .png
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge

from api_locale import modeles
from api.defense_extraction import quantifier_score
from api_locale.preprocess import pretraiter

RACINE = Path(__file__).resolve().parent.parent
SORTIES = Path(__file__).resolve().parent / "results"
SEED = 42                          # graine fixe : mêmes textes à chaque exécution, résultats reproductibles
VOLUMES = [100, 500, 1000, 2000]   # nombre de requêtes de l'attaquant ; 2000 = ordre de grandeur de l'attaque reçue


def charger_requetes_attaquant(n: int) -> list[str]:
    """Textes que l'attaquant envoie : du train, SANS les vrais labels (il ne les a pas)."""
    df = pd.read_csv(RACINE / "data" / "clean" / "train_clean.csv")
    return df.sample(n, random_state=SEED).comment_text.astype(str).tolist()


def charger_test_etiquete(n: int = 3000):
    """Jeu séparé, avec les vrais labels, pour évaluer le clone et la cible."""
    textes = pd.read_csv(RACINE / "data" / "test.csv")
    labels = pd.read_csv(RACINE / "data" / "test_labels.csv")
    df = textes.merge(labels, on="id")
    # -1 = ligne non évaluée par Kaggle : on les écarte, elles n'ont pas de vrais labels
    df = df[df[modeles.LABELS].ne(-1).all(axis=1)].sample(n, random_state=SEED)
    return df.comment_text.astype(str).tolist(), df[modeles.LABELS].to_numpy()


def interroger_cible(modele, seuils, textes, defense: bool):
    """Simule la réponse de l'API pour chaque texte : score par label, quantifié ou non."""
    s = np.array([seuils[l] for l in modeles.LABELS])      # seuil de décision de chaque label
    scores = np.zeros((len(textes), len(modeles.LABELS)))
    for i, t in enumerate(textes):
        p = modele.probabilites(pretraiter(t)) * 100
        if defense:
            p = np.array([quantifier_score(float(x), pas=100) for x in p])   # verdict pur : 0 ou 100, aucune nuance
        scores[i] = p
    detectes = (scores / 100 >= s).astype(int)      # verdict par label : score au-dessus du seuil
    return scores, detectes


def entrainer_clone(textes_entrainement, scores_cible):
    """Un petit clone : TF-IDF + régression Ridge par label, qui apprend à reproduire le
    SCORE continu renvoyé par la cible (vraie distillation, comme un attaquant réel) —
    jamais les vrais labels, que l'attaquant n'a pas. Avec la défense, le score reçu est
    quantifié : le clone apprend un signal plus pauvre, moins fidèle près du seuil."""
    vect = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
    X = vect.fit_transform(textes_entrainement)
    modeles_clone = []
    for j in range(scores_cible.shape[1]):
        y_continu = scores_cible[:, j] / 100
        reg = Ridge(alpha=1.0)
        reg.fit(X, y_continu)
        modeles_clone.append(reg)
    return vect, modeles_clone


def predire_clone(vect, modeles_clone, textes, seuils):
    """Verdict du clone sur des textes qu'il n'a jamais vus, avec les mêmes seuils que la cible."""
    X = vect.transform(textes)
    s = np.array([seuils[l] for l in modeles.LABELS])
    out = np.zeros((len(textes), len(modeles_clone)))
    for j, reg in enumerate(modeles_clone):
        out[:, j] = reg.predict(X)
    return (out >= s).astype(int)


def metriques_clone(y_vrai, pred_clone, pred_cible):
    """Accord = part des verdicts où le clone fait comme la cible (mesure de fidélité du vol) ; exactitude et faux
    positifs = qualité du clone face aux VRAIS labels."""
    accord = float((pred_clone == pred_cible).mean())
    vp = ((pred_clone == 1) & (y_vrai == 1)).sum(); fp = ((pred_clone == 1) & (y_vrai == 0)).sum()
    fn = ((pred_clone == 0) & (y_vrai == 1)).sum(); vn = ((pred_clone == 0) & (y_vrai == 0)).sum()
    exactitude = (vp + vn) / y_vrai.size
    taux_fp = fp / (fp + vn) if (fp + vn) else 0.0
    return {"accord_clone_cible": round(accord, 4), "exactitude_clone": round(float(exactitude), 4),
            "faux_positifs_clone": round(float(taux_fp), 4)}


def main():
    modele = modeles.obtenir("distilbert")
    seuils = modeles.seuils(modele)
    modele.probabilites(pretraiter("warm up"))      # première inférence lente (chargement) : on la fait avant de mesurer

    textes_test, y_test = charger_test_etiquete()
    _, pred_cible_test = interroger_cible(modele, seuils, textes_test, defense=False)   # verdict réel, jamais quantifié pour l'évaluation

    resultats = {"sans_defense": [], "avec_defense": []}
    for n in VOLUMES:      # plus l'attaquant envoie de requêtes, plus son clone devrait être fidèle
        requetes = charger_requetes_attaquant(n)
        for condition, defense in [("sans_defense", False), ("avec_defense", True)]:
            t0 = time.perf_counter()
            scores, _ = interroger_cible(modele, seuils, requetes, defense=defense)
            vect, clone = entrainer_clone(requetes, scores)
            pred_clone_test = predire_clone(vect, clone, textes_test, seuils)
            m = metriques_clone(y_test, pred_clone_test, pred_cible_test)
            m["n_requetes"] = n
            m["duree_s"] = round(time.perf_counter() - t0, 1)
            resultats[condition].append(m)
            print(f"{condition:13s} n={n:4d} | accord clone/cible {m['accord_clone_cible']:.3f} "
                  f"| exactitude {m['exactitude_clone']:.3f} | faux+ {m['faux_positifs_clone']:.3f}")

    SORTIES.mkdir(exist_ok=True)
    base = SORTIES / "extraction"
    base.with_suffix(".json").write_text(json.dumps(resultats, indent=1), encoding="utf-8")
    lignes = [{"condition": c, **m} for c, L in resultats.items() for m in L]
    pd.DataFrame(lignes).to_csv(base.with_suffix(".csv"), index=False)
    graphique(resultats, base.with_suffix(".png"))
    print("écrit :", base.with_suffix(".json"), base.with_suffix(".csv"), base.with_suffix(".png"))


def graphique(resultats: dict, chemin: Path):
    import matplotlib
    matplotlib.use("Agg")      # pas de fenêtre : on écrit seulement un fichier image
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    for condition, couleur, style in [("sans_defense", "#c0392b", "-o"), ("avec_defense", "#1a7a4a", "-s")]:
        L = resultats[condition]
        ax.plot([m["n_requetes"] for m in L], [m["accord_clone_cible"] for m in L], style, color=couleur,
                label=f"Accord clone/cible — {'sans défense' if condition == 'sans_defense' else 'avec défense'}")
    ax.set_xscale("log")      # les volumes vont de 100 à 2000 : l'échelle logarithmique les espace régulièrement
    ax.set_xlabel("Nombre de requêtes envoyées à l'API (effort de l'attaquant)")
    ax.set_ylabel("Accord clone / cible")
    ax.set_ylim(0, 1.05)
    ax.set_title("Effet de la quantification du score sur la fidélité du clone", fontsize=11, fontweight="bold")
    ax.legend(fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(chemin, dpi=140); plt.close(fig)


if __name__ == "__main__":
    main()
