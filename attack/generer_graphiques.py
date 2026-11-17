"""Parse les flux SSE sauvegardés (attack/resultats_equipes/*.sse) et produit, pour chaque
équipe : un graphique récapitulatif des 4 attaques + un CSV des évasions (pour citer des
exemples concrets dans le rapport envoyé à l'équipe visée).

Usage : .venv/bin/python attack/generer_graphiques.py
"""
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

DOSSIER = Path(__file__).resolve().parent / "resultats_equipes"
ATTAQUES = ["deguisement", "noyage", "synonymes", "mutation"]
LIBELLES = {"deguisement": "Déguisement", "noyage": "Noyage", "synonymes": "Synonymes", "mutation": "Mutation"}


def parser_sse(chemin: Path):
    """Renvoie (dernier événement 'phrase' = stats finales, liste des lignes 'phrase')."""
    lignes = []
    # Un flux SSE (Server-Sent Events) est une suite de blocs séparés par une ligne vide : « event: <type> » puis « data: <json> »
    for bloc in chemin.read_text(encoding="utf-8").split("\n\n"):
        if bloc.startswith("event: phrase"):      # un événement « phrase » = le résultat d'un commentaire testé
            lignes.append(json.loads(bloc.split("data: ", 1)[1]))
    return lignes


def resume_equipe(prefixe: str, nom_equipe: str):
    resultats = {}
    evasions_detail = []
    for att in ATTAQUES:
        chemin = DOSSIER / f"{prefixe}_{att}.sse"
        if not chemin.exists():
            continue
        lignes = parser_sse(chemin)
        derniere = lignes[-1]      # les compteurs de la dernière ligne sont cumulés : ce sont les résultats finaux
        resultats[att] = {
            "rappel_avant": derniere["rappel_avant"],
            "rappel_apres": derniere["rappel_apres"],
            "evasions": derniere["evasions"],
            "latence_moyenne": derniere["latence_moyenne"],
        }
        for l in lignes:      # on garde le détail des évasions, pour citer des exemples concrets à l'équipe visée
            if l.get("evasion"):
                evasions_detail.append({"attaque": LIBELLES[att], "commentaire_original": l["texte"],
                                        "texte_envoye": l["piege"], "score_avant": l["score_avant"],
                                        "score_apres": l["score_apres"]})
    return resultats, evasions_detail


def graphique(resultats: dict, nom_equipe: str, chemin_png: Path):
    noms = [LIBELLES[a] for a in ATTAQUES if a in resultats]
    rappel_avant = [resultats[a]["rappel_avant"] * 100 for a in ATTAQUES if a in resultats]
    rappel_apres = [resultats[a]["rappel_apres"] * 100 for a in ATTAQUES if a in resultats]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = range(len(noms))      # deux barres par attaque : rappel avant (vert) et après (rouge)
    ax.bar([i - 0.2 for i in x], rappel_avant, width=0.4, label="Avant attaque", color="#1f8f5f")
    barres = ax.bar([i + 0.2 for i in x], rappel_apres, width=0.4, label="Après attaque", color="#d23b3b")
    ax.bar_label(barres, fmt="%.0f%%", fontsize=8, padding=2)
    ax.set_xticks(list(x), noms)
    ax.set_ylabel("Rappel sur les 15 commentaires toxiques (%)")
    ax.set_ylim(0, 105)
    ax.set_title(f"Détection avant/après attaque — {nom_equipe}", fontsize=11, fontweight="bold")
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(chemin_png, dpi=140)
    plt.close(fig)
    print("écrit :", chemin_png)


if __name__ == "__main__":
    for prefixe, nom in [("florentin", "Florentin & Gilane"), ("exauce", "Exauce & Gilbert")]:
        resultats, evasions = resume_equipe(prefixe, nom)
        if not resultats:
            continue
        print(f"\n=== {nom} ===")
        for att, r in resultats.items():
            print(f"{LIBELLES[att]:12s} rappel {r['rappel_avant']:.0%} -> {r['rappel_apres']:.0%} "
                  f"| {r['evasions']}/15 évasions | latence {r['latence_moyenne']:.0f} ms")
        graphique(resultats, nom, DOSSIER / f"{prefixe}_resultats.png")
        pd.DataFrame(evasions).to_csv(DOSSIER / f"{prefixe}_evasions.csv", index=False)
        print("écrit :", DOSSIER / f"{prefixe}_evasions.csv", f"({len(evasions)} lignes)")
