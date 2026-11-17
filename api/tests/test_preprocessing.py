"""Tests du prétraitement + test de parité avec les fichiers produits par les notebooks.

Le test de parité garantit qu'en production l'API transforme le texte EXACTEMENT
comme à l'entraînement (pas de « training/serving skew »).
"""
from pathlib import Path

import pandas as pd
import pytest

from preprocessing import anonymize, preprocess

RACINE = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("brut, attendu", [
    ("Your vandalism to the Matt Shirvington article has been reverted.",
     "your vandalism to the personne_tag article has been reverted"),
    ("I'm retired now.89.205.38.27", "i m retired now ip_tag"),
    ("see User:Physicq210, thanks", "see user pseudo_tag thanks"),
    ("HOLA FUCKER", "hola fucker"),                       # insulte non masquée
    ("go back to Mexico you stupid Muslim", "go back to mexico you stupid muslim"),  # lieu et groupe gardés
])
def test_preprocess(brut, attendu):
    assert preprocess(brut) == attendu


def test_pas_de_fuite_ip_email():
    sortie = anonymize("contact me at bob.doe@gmail.com from 10.0.0.1")
    assert "bob.doe" not in sortie and "10.0.0.1" not in sortie


@pytest.mark.skipif(not (RACINE / "data" / "clean" / "train_clean.csv").exists(),
                    reason="data/clean absent (lancer anonyme_2 puis clean_text)")
def test_parite_avec_les_notebooks():
    brut = pd.read_csv(RACINE / "data" / "train.csv").set_index("id")
    propre = pd.read_csv(RACINE / "data" / "clean" / "train_clean.csv").set_index("id")
    ids = propre.sample(50, random_state=0).index
    for i in ids:
        attendu = propre.loc[i, "comment_text"]
        attendu = "" if pd.isna(attendu) else str(attendu)   # texte vide relu comme NaN par pandas
        assert preprocess(str(brut.loc[i, "comment_text"])) == attendu
