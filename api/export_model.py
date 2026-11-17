"""Copie le modèle entraîné (models/ à la racine du repo) dans api/model/ et écrit meta.json.

À lancer depuis la racine du repo, après notebooks/train.ipynb :
    python api/export_model.py --type bilstm
    python api/export_model.py --type distilbert
    python api/export_model.py --type laya          # rien à copier : télécharge le checkpoint public
"""
import argparse
import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(API_DIR))
from preprocessing import PREPROCESSING_VERSION  # noqa: E402

RACINE = API_DIR.parent
# Hyperparamètres fixés dans notebooks/train.ipynb (à garder synchronisés)
PARAMS = {
    "bilstm": {"source": RACINE / "models" / "bilstm", "max_len": 200, "emb_dim": 128, "hidden": 64},
    "distilbert": {"source": RACINE / "models" / "distilbert", "max_len": 128},
    "laya": {"source": None, "checkpoint": "convaiinnovations/laya"},
}
# Questions de LAYA : copie EXACTE de QUESTIONS_LAYA dans notebooks/train.ipynb
QUESTIONS_LAYA = {
    "toxic": "Is this comment toxic?",
    "severe_toxic": "Is this comment severely toxic?",
    "obscene": "Does this comment contain obscene language?",
    "threat": "Does this comment contain a threat?",
    "insult": "Does this comment contain an insult?",
    "identity_hate": "Does this comment contain identity-based hate?",
}

# Nom de chaque modèle dans models/seuils.json (écrit par le notebook d'entraînement)
NOMS_SEUILS = {"bilstm": "BiLSTM", "distilbert": "DistilBERT", "laya": "LAYA (zéro-shot)"}

parser = argparse.ArgumentParser()
parser.add_argument("--type", choices=PARAMS, required=True)
args = parser.parse_args()

params = dict(PARAMS[args.type])
source = params.pop("source")
cible = API_DIR / "model"
shutil.rmtree(cible, ignore_errors=True)
if args.type == "laya":
    # Pré-téléchargement du checkpoint dans model/hf_cache : il partira DANS l'image Docker
    os.environ["HF_HOME"] = str(cible / "hf_cache")
    import laya
    laya.load(params["checkpoint"])
    params["questions"] = QUESTIONS_LAYA
else:
    if not source.exists():
        sys.exit(f"Modèle introuvable : {source} (lancer d'abord notebooks/train.ipynb)")
    shutil.copytree(source, cible)

# Seuils de décision par label, choisis sur la validation (sinon 0,5 par défaut dans l'API)
fichier_seuils = RACINE / "models" / "seuils.json"
if fichier_seuils.exists():
    tous = json.loads(fichier_seuils.read_text(encoding="utf-8"))
    params["seuils"] = {l: round(float(s), 4) for l, s in tous.get(NOMS_SEUILS[args.type], {}).items()}
if not params.get("seuils"):
    print("ATTENTION : pas de seuils pour ce modèle, l'API utilisera 0,5 pour chaque label")

meta = {
    "model_type": args.type,
    "model_version": f"{args.type}{'-zero-shot' if args.type == 'laya' else ''}-{date.today().isoformat()}",
    "preprocessing_version": PREPROCESSING_VERSION,
    "labels": ["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"],
    **params,
}
(cible / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
(cible / ".gitkeep").touch()   # garde le dossier dans Git (son contenu est ignoré)
print(f"Modèle copié dans {cible} :", json.dumps(meta, indent=2))