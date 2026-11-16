"""Recalcule models/seuils.json à partir des prédictions enregistrées par notebooks/train.ipynb.

Utile pour avoir les seuils sans attendre la dernière cellule du notebook (qui les écrit aussi, avec le même calcul).
Usage : .venv/bin/python -m api.export_seuils
"""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split

from api.modeles import DOSSIER_MODELES, LABELS, RACINE

SEED = 42
# fichier de prédictions de validation -> nom du modèle dans seuils.json
FICHIERS = {"bilstm": "BiLSTM", "distilbert": "DistilBERT", "laya__zéro_shot": "LAYA (zéro-shot)"}

df = pd.read_csv(RACINE / "data" / "clean" / "train_clean.csv")
Y = df[LABELS].to_numpy(dtype=np.float32)
_, idx_val = train_test_split(np.arange(len(df)), test_size=0.2, random_state=SEED)   # même split que le notebook
grille = np.arange(0.02, 0.99, 0.01)

chemin = DOSSIER_MODELES / "seuils.json"
resultat = json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else {}
for prefixe, nom in FICHIERS.items():
    fichier = DOSSIER_MODELES / "predictions" / f"{prefixe}_validation.npy"
    if not fichier.exists():
        continue
    proba = np.load(fichier)
    y = Y[idx_val][:len(proba)]            # LAYA n'est évalué que sur les premières lignes de la validation
    seuils = {}
    for j, label in enumerate(LABELS):
        f1s = [f1_score(y[:, j], (proba[:, j] >= s).astype(int), zero_division=0) for s in grille]
        seuils[label] = round(float(grille[int(np.argmax(f1s))]), 2)
    resultat[nom] = seuils
    print(nom, seuils)
chemin.write_text(json.dumps(resultat, indent=1), encoding="utf-8")
print("écrit :", chemin)
