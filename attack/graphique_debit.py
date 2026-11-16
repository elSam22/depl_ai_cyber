"""Graphique du test de débit (attack/debit.py), pour le livrable étape 3.
Usage : .venv/bin/python -m attack.graphique_debit
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SORTIES = Path(__file__).resolve().parent / "results"

# Résultats mesurés (attack/debit.py, rafale de 20 s) : voir attack/RAPPORT.md § 5.3
DONNEES = {
    "Sans limiteur": {"200 OK": 1442, "429 rejetées": 0},
    "Avec limiteur (60 req/60 s)": {"200 OK": 60, "429 rejetées": 30507},
}


def main():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.8), gridspec_kw={"width_ratios": [1, 1.3]})
    noms = list(DONNEES)

    # Requêtes exploitables obtenues (échelle linéaire, c'est le chiffre qui compte pour l'attaquant)
    exploitables = [DONNEES[n]["200 OK"] for n in noms]
    barres = a1.bar(noms, exploitables, color=["#c0392b", "#1a7a4a"])
    a1.bar_label(barres, fmt="%d", fontsize=11, padding=3)
    a1.set_ylabel("Requêtes exploitables obtenues en 20 s")
    a1.set_title("Effort utile pour l'attaquant", fontsize=10)
    a1.spines[["top", "right"]].set_visible(False)
    a1.set_ylim(0, max(exploitables) * 1.2)

    # Répartition 200 / 429 (empilé), échelle log pour voir les deux barres malgré l'écart x500
    import numpy as np
    x = np.arange(len(noms))
    ok = [DONNEES[n]["200 OK"] for n in noms]
    rejet = [DONNEES[n]["429 rejetées"] for n in noms]
    a2.bar(x, ok, label="200 OK (exploitable)", color="#1a7a4a")
    a2.bar(x, rejet, bottom=ok, label="429 rejetées", color="#888880")
    a2.set_xticks(x, noms)
    a2.set_ylabel("Requêtes totales en 20 s")
    a2.set_title("Ce que devient chaque requête", fontsize=10)
    a2.legend(fontsize=8)
    a2.spines[["top", "right"]].set_visible(False)

    fig.suptitle("Effet du limiteur de débit sur une rafale de 20 s (attack/debit.py)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout()
    chemin = SORTIES / "debit.png"
    fig.savefig(chemin, dpi=140)
    print("écrit :", chemin)


if __name__ == "__main__":
    main()
