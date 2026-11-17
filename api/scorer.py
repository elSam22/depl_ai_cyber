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
            # 0,3 par mot grossier, plafonné à 1 ; `toxic` et `insult` reçoivent la valeur entière, les autres un tiers
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
                masque = (x != 0).unsqueeze(-1)              # 0 = remplissage (padding) : à ignorer
                h, _ = self.lstm(self.embedding(x))
                h = h.masked_fill(~masque, -1e9)             # le remplissage ne peut jamais gagner le max-pooling
                return self.sortie(self.dropout(h.max(dim=1).values))

        self.model = BiLSTM(len(self.vocab), meta["emb_dim"], meta["hidden"], len(LABELS))
        self.model.load_state_dict(torch.load(model_dir / "bilstm.pt", map_location="cpu", weights_only=True))
        self.model.eval()

    def _encoder(self, texts: list[str]):
        """Copie exacte de encoder() dans train.ipynb."""
        X = self.torch.zeros((len(texts), self.max_len), dtype=self.torch.long)
        for i, t in enumerate(texts):
            # Mot inconnu -> indice 1 ; texte vide -> un seul mot inconnu ; texte trop long -> tronqué à max_len mots
            ids = [self.vocab.get(m, 1) for m in t.split()[:self.max_len]] or [1]
            X[i, :len(ids)] = self.torch.tensor(ids)
        return X

    def predict(self, texts: list[str]) -> list[dict[str, float]]:
        with self.torch.no_grad():
            probas = self.torch.sigmoid(self.model(self._encoder(texts))).tolist()
        return [dict(zip(LABELS, p)) for p in probas]


# Défense anti-noyage (TP2, étape 3) : longueur des fenêtres d'analyse, en tokens. Mesure (60 insultes noyées après
# 1 000 / 3 000 caractères neutres ; 300 vrais textes sains de 400 à 5 000 caractères) : fenêtres de 128 -> 30 et 38
# détectées sur 60, 9 % de fausses alertes ; de 64 -> 38 et 45 sur 60, 12 % ; de 32 -> 47 et 51 sur 60, 15 %
# (avant : 4 et 2 sur 60, 4 %). 64 = compromis retenu. Réglable sans reconstruire l'image (variable d'environnement).
FENETRE_NOYAGE = int(os.environ.get("FENETRE_NOYAGE", "64"))
# Chevauchement entre fenêtres : 16 (et non 32) mesuré aussi efficace (40 et 48 insultes sur 60 au lieu de 38 et 45,
# mêmes fausses alertes) pour 21 fenêtres au lieu de 32 sur un texte de 5 000 caractères : le coût d'un texte long
# (mesuré 5,3 à 6,8 s sur le pod avec 32) baisse d'un tiers.
CHEVAUCHEMENT_NOYAGE = int(os.environ.get("CHEVAUCHEMENT_NOYAGE", "16"))


class DistilBertScorer:
    """DistilBERT fine-tuné de notebooks/train.ipynb (dossier save_pretrained)."""

    def __init__(self, model_dir: Path, meta: dict):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.version = meta["model_version"]
        self.max_len = meta["max_len"]
        # Dossier LOCAL embarqué dans l'image (HF_HUB_OFFLINE=1) : aucun téléchargement, donc pas de révision à épingler
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)  # nosec B615
        # Un seul fil de calcul : le pod n'a droit qu'à 1 CPU ; PyTorch en lance par défaut autant que de cœurs de la
        # machine, et le quota Kubernetes les freine tous (temps perdu). Réglable par TORCH_THREADS.
        torch.set_num_threads(int(os.environ.get("TORCH_THREADS", "1")))
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir)  # nosec B615
        self.model.eval()

    def _passe(self, texts: list[str], longueur: int, chevauchement: int | None = None):
        """Probabilités par texte. Avec `chevauchement`, le texte est découpé en fenêtres de `longueur` tokens qui se
        recouvrent, toutes évaluées en un seul passage, et chaque label garde son MAXIMUM sur les fenêtres."""
        options = dict(truncation=True, max_length=longueur, padding=True, return_tensors="pt")
        if chevauchement is not None:
            # stride = nombre de tokens communs entre deux fenêtres voisines ; return_overflowing_tokens rend TOUTES les
            # fenêtres au lieu de jeter ce qui dépasse.
            options.update(stride=chevauchement, return_overflowing_tokens=True)
        enc = self.tokenizer(texts, **options)
        origine = enc.pop("overflow_to_sample_mapping", None)     # fenêtre -> numéro du texte d'où elle vient ; à retirer avant le modèle
        with self.torch.no_grad():
            probas = self.torch.sigmoid(self.model(**enc).logits).tolist()
        origine = origine.tolist() if origine is not None else range(len(texts))
        maxima = [[0.0] * len(LABELS) for _ in texts]
        for i, p in zip(origine, probas):      # plusieurs fenêtres pour un même texte : max par label
            maxima[i] = [max(x, y) for x, y in zip(maxima[i], p)]
        return maxima, len(probas)

    def predict(self, texts: list[str]) -> list[dict[str, float]]:
        """1. Passe complète, comme à l'entraînement (le texte est tronqué à max_len tokens).
        2. Défense anti-noyage : si le texte dépasse FENETRE_NOYAGE tokens, il est AUSSI lu par fenêtres de
           FENETRE_NOYAGE tokens chevauchantes. Sans cela, une insulte placée après ~1 000 caractères neutres n'était
           jamais vue (troncature), et même dans un texte de taille normale elle était diluée par le texte neutre.
        Chaque label garde le maximum des deux lectures. Un texte court ne fait qu'une passe : rien ne change pour lui.
        Coût : proportionnel à la longueur, plafonné par MAX_CHARS (5 000 caractères)."""
        complet, n = self._passe(texts, self.max_len)
        # Longueur réelle en tokens (sans troncature) : seuls les textes plus longs qu'une fenêtre sont relus.
        longueurs = [len(ids) for ids in self.tokenizer(texts, add_special_tokens=False)["input_ids"]]
        longs = [i for i, lg in enumerate(longueurs) if lg > FENETRE_NOYAGE]
        if longs:
            fenetres, m = self._passe([texts[i] for i in longs], FENETRE_NOYAGE, CHEVAUCHEMENT_NOYAGE)
            for i, f in zip(longs, fenetres):
                complet[i] = [max(x, y) for x, y in zip(complet[i], f)]
            n += m
        self.dernier_nb_passes = n            # nombre de séquences évaluées (tests, mesure du coût)
        return [dict(zip(LABELS, p)) for p in complet]


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
    if not meta_path.exists():      # pas de modèle exporté : modèle factice (développement et tests de l'API)
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
    # Seuils de décision par label, choisis sur la validation (api/model/meta.json, venu de models/seuils.json)
    scorer.seuils = _seuils(meta)
    return scorer