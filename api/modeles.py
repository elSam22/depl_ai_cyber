"""Chargement des modèles entraînés (BiLSTM, DistilBERT, LAYA) et prédiction sur UN texte déjà prétraité.

Chaque modèle expose `probabilites(texte)` : un tableau de 6 probabilités, dans l'ordre de LABELS.
Les modèles sont chargés à la première utilisation (LAYA pèse ~800 Mo et met environ 1 minute à charger).
"""
import os
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")   # avant d'importer torch
os.environ.setdefault("USE_TF", "0")

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_MODELES = RACINE / "models"
LABELS = ["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"]
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

# Hyperparamètres identiques à ceux de notebooks/train.ipynb
LONGUEUR_LSTM, EMB_LSTM, HIDDEN_LSTM = 200, 128, 64
LONGUEUR_BERT = 128


class ModeleIndisponible(Exception):
    """Le modèle demandé n'est pas disponible (fichiers absents ou librairie manquante)."""


class BiLSTM(nn.Module):
    """Embedding 128 -> LSTM bidirectionnel (64 par sens) -> max-pooling -> 6 logits (copie du notebook)."""

    def __init__(self, taille_vocab, emb=EMB_LSTM, hidden=HIDDEN_LSTM, n_labels=len(LABELS)):
        super().__init__()
        self.embedding = nn.Embedding(taille_vocab, emb, padding_idx=0)
        self.lstm = nn.LSTM(emb, hidden, batch_first=True, bidirectional=True)
        self.dropout = nn.Dropout(0.3)
        self.sortie = nn.Linear(2 * hidden, n_labels)

    def forward(self, x):
        masque = (x != 0).unsqueeze(-1)
        h, _ = self.lstm(self.embedding(x))
        h = h.masked_fill(~masque, -1e9)
        return self.sortie(self.dropout(h.max(dim=1).values))


class ModeleBiLSTM:
    nom_seuils = "BiLSTM"

    def __init__(self):
        dossier = DOSSIER_MODELES / "bilstm"
        if not (dossier / "bilstm.pt").exists():
            raise ModeleIndisponible(f"{dossier / 'bilstm.pt'} introuvable : entraîner le modèle avec notebooks/train.ipynb")
        self.vocab = json.loads((dossier / "vocab.json").read_text(encoding="utf-8"))
        self.modele = BiLSTM(len(self.vocab))
        self.modele.load_state_dict(torch.load(dossier / "bilstm.pt", map_location="cpu"))
        self.modele.to(DEVICE).eval()

    @torch.no_grad()
    def probabilites(self, texte: str) -> np.ndarray:
        ids = [self.vocab.get(m, 1) for m in texte.split()[:LONGUEUR_LSTM]] or [1]   # texte vide -> un jeton <unk>
        x = torch.zeros((1, LONGUEUR_LSTM), dtype=torch.long)
        x[0, :len(ids)] = torch.tensor(ids)
        return torch.sigmoid(self.modele(x.to(DEVICE)))[0].cpu().numpy()


class ModeleDistilBERT:
    nom_seuils = "DistilBERT"

    def __init__(self):
        dossier = DOSSIER_MODELES / "distilbert"
        if not (dossier / "model.safetensors").exists():
            raise ModeleIndisponible(f"{dossier} introuvable : lancer notebooks/train.ipynb (entraînement de DistilBERT)")
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        self.tokenizer = AutoTokenizer.from_pretrained(dossier)
        self.modele = AutoModelForSequenceClassification.from_pretrained(dossier).to(DEVICE).eval()

    @torch.no_grad()
    def probabilites(self, texte: str) -> np.ndarray:
        enc = self.tokenizer([texte], truncation=True, padding="max_length", max_length=LONGUEUR_BERT, return_tensors="pt")
        logits = self.modele(input_ids=enc["input_ids"].to(DEVICE), attention_mask=enc["attention_mask"].to(DEVICE)).logits
        return torch.sigmoid(logits)[0].cpu().numpy()


class ModeleLaya:
    """LAYA zéro-shot : une question oui/non par label (voir la section LAYA de notebooks/train.ipynb). Lent (~0,3 s)."""
    nom_seuils = "LAYA (zéro-shot)"
    QUESTIONS = {
        "toxic": "Is this comment toxic?",
        "severe_toxic": "Is this comment severely toxic?",
        "obscene": "Does this comment contain obscene language?",
        "threat": "Does this comment contain a threat?",
        "insult": "Does this comment contain an insult?",
        "identity_hate": "Does this comment contain identity-based hate?",
    }

    def __init__(self):
        try:
            import laya
        except ImportError as e:
            raise ModeleIndisponible("la librairie laya n'est pas installée (pip install laya)") from e
        self.questions = {l: {"type": "noul", "instructions": q} for l, q in self.QUESTIONS.items()}
        self.agent = laya.load("convaiinnovations/laya")

    def probabilites(self, texte: str) -> np.ndarray:
        reponses = self.agent.predict(texte, self.questions)["answers"]
        return np.array([reponses[l]["noul"] for l in LABELS], dtype=np.float32)


CLASSES = {"bilstm": ModeleBiLSTM, "distilbert": ModeleDistilBERT, "laya": ModeleLaya}
_CHARGES = {}   # modèles déjà chargés


def obtenir(nom: str):
    """Renvoie le modèle (chargé à la première demande). Lève ModeleIndisponible s'il ne peut pas être chargé."""
    if nom not in _CHARGES:
        _CHARGES[nom] = CLASSES[nom]()
    return _CHARGES[nom]


def disponibles() -> dict:
    """Pour chaque modèle : les fichiers nécessaires sont-ils présents ? (sans le charger)."""
    return {
        "bilstm": (DOSSIER_MODELES / "bilstm" / "bilstm.pt").exists(),
        "distilbert": (DOSSIER_MODELES / "distilbert" / "model.safetensors").exists(),
        "laya": True,   # téléchargé à la première utilisation
    }


def seuils(modele) -> dict | None:
    """Seuils par label choisis sur la validation (models/seuils.json), ou None s'ils n'existent pas encore."""
    chemin = DOSSIER_MODELES / "seuils.json"
    if not chemin.exists():
        return None
    return json.loads(chemin.read_text(encoding="utf-8")).get(modele.nom_seuils)
