"""TP2, étape 3 : mesure l'effet de la défense anti-noyage (fenêtres glissantes dans api/modeles.py).

Principe de l'attaque noyage : on envoie un long texte neutre AVANT le commentaire toxique,
ce qui fait que le tokenizer (tronquant à droite) ne voit que du neutre → proba toxic chute.

La défense : scan en fenêtres glissantes de 128 tokens (DistilBERT) ou 200 mots (BiLSTM),
prise du MAX des probas sur toutes les fenêtres → le contenu toxique est détecté peu importe
sa position dans le texte.

Usage : .venv/bin/python -m attack.defense_noyage
"""
import sys
from pathlib import Path
import os

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("USE_TF", "0")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SORTIES = Path(__file__).resolve().parent / "results"
SORTIES.mkdir(exist_ok=True)

# --- Corpus de test : phrases toxiques noyées dans des préfixes neutres de taille croissante
PHRASES_TOXIQUES = [
    "You are a stupid idiot and I hate you.",
    "Kill yourself you worthless piece of trash.",
    "You are disgusting and nobody likes you.",
    "Go die in a fire you absolute moron.",
    "I will destroy you, you pathetic loser.",
]

NEUTRE_UNIT = (
    "The weather today is sunny and pleasant. "
    "I enjoy reading books in the afternoon. "
    "The cat sat on the mat near the window. "
)

NIVEAUX_REMBOURRAGE = [0, 500, 1000, 2000, 4000]  # caractères neutres ajoutés avant la phrase toxique


def construire_texte_noye(phrase_toxique: str, n_chars: int) -> str:
    if n_chars == 0:
        return phrase_toxique
    prefixe = (NEUTRE_UNIT * (n_chars // len(NEUTRE_UNIT) + 1))[:n_chars]
    return prefixe + " " + phrase_toxique


def _sans_defense(modele, texte: str) -> float:
    """Simule l'ancien comportement (tronquage droit) pour DistilBERT."""
    from api.modeles import LONGUEUR_BERT, DEVICE
    enc = modele.tokenizer(
        [texte], truncation=True, padding="max_length",
        max_length=LONGUEUR_BERT, return_tensors="pt"
    )
    import torch
    logits = modele.modele(
        input_ids=enc["input_ids"].to(DEVICE),
        attention_mask=enc["attention_mask"].to(DEVICE)
    ).logits
    return float(torch.sigmoid(logits)[0][0].cpu())


def _avec_defense(modele, texte: str) -> float:
    """Utilise la nouvelle méthode (fenêtres glissantes)."""
    return float(modele.probabilites(texte)[0])  # indice 0 = toxic


def main():
    from api.modeles import obtenir

    print("Chargement de DistilBERT…", flush=True)
    modele = obtenir("distilbert")
    print("OK\n")

    resultats = []
    for n in NIVEAUX_REMBOURRAGE:
        probas_sans = []
        probas_avec = []
        for phrase in PHRASES_TOXIQUES:
            texte = construire_texte_noye(phrase, n)
            probas_sans.append(_sans_defense(modele, texte))
            probas_avec.append(_avec_defense(modele, texte))
        moy_sans = round(np.mean(probas_sans), 3)
        moy_avec = round(np.mean(probas_avec), 3)
        evasion_sans = round(100 * sum(p < 0.5 for p in probas_sans) / len(probas_sans))
        evasion_avec = round(100 * sum(p < 0.5 for p in probas_avec) / len(probas_avec))
        print(f"Rembourrage {n:5d} chars | sans défense : {moy_sans:.3f} ({evasion_sans}% évasion) "
              f"| avec défense : {moy_avec:.3f} ({evasion_avec}% évasion)")
        resultats.append({
            "rembourrage_chars": n,
            "proba_sans_defense": moy_sans,
            "proba_avec_defense": moy_avec,
            "evasion_sans_defense_pct": evasion_sans,
            "evasion_avec_defense_pct": evasion_avec,
        })

    # Sauvegarde JSON
    (SORTIES / "defense_noyage.json").write_text(
        json.dumps(resultats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- Graphique
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.8))
    niveaux = [r["rembourrage_chars"] for r in resultats]

    a1.plot(niveaux, [r["proba_sans_defense"] for r in resultats],
            "o--", color="#c0392b", label="Sans défense (tronquage droit)")
    a1.plot(niveaux, [r["proba_avec_defense"] for r in resultats],
            "s-", color="#1a7a4a", label="Avec défense (fenêtres glissantes)")
    a1.axhline(0.5, linestyle=":", color="#888", linewidth=0.8, label="Seuil de décision (0,5)")
    a1.set_xlabel("Caractères neutres ajoutés avant le texte toxique")
    a1.set_ylabel("Probabilité « toxic » (moyenne sur 5 phrases)")
    a1.set_title("Effet du noyage sur la proba toxique", fontsize=10)
    a1.legend(fontsize=8)
    a1.spines[["top", "right"]].set_visible(False)

    a2.bar(
        [str(n) for n in niveaux],
        [r["evasion_sans_defense_pct"] for r in resultats],
        color="#c0392b", alpha=0.7, label="Sans défense"
    )
    a2.bar(
        [str(n) for n in niveaux],
        [r["evasion_avec_defense_pct"] for r in resultats],
        color="#1a7a4a", alpha=0.9, label="Avec défense"
    )
    a2.set_xlabel("Caractères neutres ajoutés")
    a2.set_ylabel("Taux d'évasion (%)")
    a2.set_title("Taux d'évasion avant / après défense", fontsize=10)
    a2.legend(fontsize=8)
    a2.spines[["top", "right"]].set_visible(False)

    fig.suptitle("Défense anti-noyage : fenêtres glissantes sur DistilBERT (api/modeles.py)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout()
    chemin = SORTIES / "defense_noyage.png"
    fig.savefig(chemin, dpi=140)
    print(f"\nGraphique écrit : {chemin}")


if __name__ == "__main__":
    main()
