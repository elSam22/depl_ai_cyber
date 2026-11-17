"""Recalcule la ROC-AUC et l'AUC-PR (macro sur les 6 labels) des trois modèles, sur le test commun (TP1, § 3.3).

Utilise les probabilités enregistrées par notebooks/train.ipynb (models/predictions/<modèle>_test.npy) et le même
test commun que le notebook : test_labels.csv sans les lignes à -1, puis 10 000 lignes tirées avec la graine 42.
La ROC-AUC obtenue doit être identique à celle du notebook : c'est la preuve que l'échantillon est le bon.
Lancement (depuis la racine) : .venv/bin/python outils/calculer_auc_pr.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

RACINE = Path(__file__).resolve().parent.parent
LABELS = ["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"]
MODELES = {"BiLSTM": "bilstm", "DistilBERT": "distilbert", "LAYA (zéro-shot)": "laya__zéro_shot"}

etiquettes = pd.read_csv(RACINE / "data" / "test_labels.csv")
non_evalue = (etiquettes[LABELS] == -1).all(axis=1).to_numpy()
y = etiquettes[LABELS].to_numpy(dtype=np.float32)[~non_evalue]
y = y[np.sort(np.random.RandomState(42).choice(len(y), 10_000, replace=False))]

print(f"{'modèle':<18} {'ROC-AUC':>8} {'AUC-PR':>8}")
for nom, fichier in MODELES.items():
    p = np.load(RACINE / "models" / "predictions" / f"{fichier}_test.npy")
    roc = np.mean([roc_auc_score(y[:, i], p[:, i]) for i in range(len(LABELS))])
    ap = np.mean([average_precision_score(y[:, i], p[:, i]) for i in range(len(LABELS))])
    print(f"{nom:<18} {roc:>8.4f} {ap:>8.3f}")
