"""Chargement du modèle et prédiction.

L'API ne connaît qu'une interface : `scorer.predict(textes_pretraites) -> probabilités des 6 labels`.
Le type de modèle est lu dans model/meta.json (écrit par export_model.py) :
    - pas de meta.json      -> DummyScorer (modèle factice, pour développer l'API)
    - "model_type": "bilstm"     -> BiLSTMScorer      (poids de notebooks/train.ipynb)
    - "model_type": "distilbert" -> DistilBertScorer  (dossier save_pretrained de train.ipynb)
    - "model_type": "laya"       -> LayaScorer        (zéro-shot, mêmes questions que train.ipynb)

Les textes reçus ici sont DÉJÀ prétraités (anonymisés + nettoyés) par preprocessing.py.
"""
import json
import os
from pathlib import Path

from preprocessing import PREPROCESSING_VERSION

LABELS = ["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"]
MODEL_DIR = Path(os.environ.get("MODEL_DIR", Path(__file__).parent / "model"))
SEUIL_PAR_DEFAUT = 0.5


def _seuils(meta: dict) -> dict[str, float]:
    """Seuil de décision par label (meta.json), 0,5 si absent."""
    return {l: float(meta.get("seuils", {}).get(l, SEUIL_PAR_DEFAUT)) for l in LABELS}


class DummyScorer:
    """Modèle FACTICE : compte quelques mots grossiers. Sert uniquement à tester l'API."""

    version = "dummy-0"
    _MOTS = {"idiot", "stupid", "moron", "fuck", "shit", "hate", "kill", "die"}

    def predict(self, texts: list[str]) -> list[dict[str, float]]:
        sorties = []
        for t in texts:
            p = min(1.0, 0.3 * sum(mot in self._MOTS for mot in t.split()))
            sorties.append({label: (p if label in ("toxic", "insult") else p / 3) for label in LABELS})
        return sorties


class BiLSTMScorer:
    """BiLSTM de notebooks/train.ipynb : MÊME architecture et MÊME encodage qu'à l'entraînement."""

    def __init__(self, model_dir: Path, meta: dict):
        import torch
        import torch.nn as nn

        self.torch = torch
        self.version = meta["model_version"]
        self.max_len = meta["max_len"]
        self.vocab = json.loads((model_dir / "vocab.json").read_text(encoding="utf-8"))

        class BiLSTM(nn.Module):
            # Noms des couches identiques à train.ipynb, sinon load_state_dict échoue
            def __init__(self, taille_vocab, emb, hidden, n_labels):
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

        self.model = BiLSTM(len(self.vocab), meta["emb_dim"], meta["hidden"], len(LABELS))
        self.model.load_state_dict(torch.load(model_dir / "bilstm.pt", map_location="cpu"))
        self.model.eval()

    def _encoder(self, texts: list[str]):
        """Copie exacte de encoder() dans train.ipynb."""
        X = self.torch.zeros((len(texts), self.max_len), dtype=self.torch.long)
        for i, t in enumerate(texts):
            ids = [self.vocab.get(m, 1) for m in t.split()[:self.max_len]] or [1]
            X[i, :len(ids)] = self.torch.tensor(ids)
        return X

    def predict(self, texts: list[str]) -> list[dict[str, float]]:
        with self.torch.no_grad():
            probas = self.torch.sigmoid(self.model(self._encoder(texts))).tolist()
        return [dict(zip(LABELS, p)) for p in probas]


class DistilBertScorer:
    """DistilBERT fine-tuné de notebooks/train.ipynb (dossier save_pretrained)."""

    def __init__(self, model_dir: Path, meta: dict):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.version = meta["model_version"]
        self.max_len = meta["max_len"]
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        self.model.eval()

    def predict(self, texts: list[str]) -> list[dict[str, float]]:
        enc = self.tokenizer(texts, truncation=True, max_length=self.max_len, padding=True, return_tensors="pt")
        with self.torch.no_grad():
            probas = self.torch.sigmoid(self.model(**enc).logits).tolist()
        return [dict(zip(LABELS, p)) for p in probas]


class LayaScorer:
    """LAYA en zéro-shot : copie de predire_laya() de notebooks/train.ipynb.

    Une question oui/non ("noul") par label ; la probabilité de « oui » sert de score.
    Les poids (checkpoint public) sont pré-téléchargés dans model/hf_cache par export_model.py
    et lus hors ligne (HF_HUB_OFFLINE=1 dans le Dockerfile) : aucun appel à Hugging Face en production.
    """

    def __init__(self, model_dir: Path, meta: dict):
        import laya

        self.version = meta["model_version"]
        self.questions = {label: {"type": "noul", "instructions": q} for label, q in meta["questions"].items()}
        local = model_dir / meta["checkpoint"]          # dossier embarqué dans l'image
        self.agent = laya.load(str(local) if local.exists() else meta["checkpoint"])

    def predict(self, texts: list[str]) -> list[dict[str, float]]:
        sorties = []
        for t in texts:
            reponses = self.agent.predict(t, self.questions)["answers"]
            sorties.append({label: float(reponses[label]["noul"]) for label in LABELS})
        return sorties


SCORERS = {"bilstm": BiLSTMScorer, "distilbert": DistilBertScorer, "laya": LayaScorer}


def load_scorer():
    """Charge le modèle décrit par model/meta.json (une seule fois, au démarrage de l'API)."""
    meta_path = MODEL_DIR / "meta.json"
    if not meta_path.exists():
        factice = DummyScorer()
        factice.seuils = _seuils({})
        return factice
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # Garde-fou anti "training/serving skew" : le modèle doit avoir été entraîné
    # avec la même version du prétraitement que celle embarquée dans l'API.
    if meta["preprocessing_version"] != PREPROCESSING_VERSION:
        raise RuntimeError(
            f"Prétraitement incompatible : modèle entraîné avec la v{meta['preprocessing_version']}, "
            f"API en v{PREPROCESSING_VERSION}. Ré-entraîner ou redéployer la bonne version."
        )
    if meta["model_type"] not in SCORERS:
        raise RuntimeError(f"model_type inconnu dans meta.json : {meta['model_type']}")
    scorer = SCORERS[meta["model_type"]](MODEL_DIR, meta)
    scorer.seuils = _seuils(meta)
    return scorer