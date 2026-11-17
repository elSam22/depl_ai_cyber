# API locale de développement

Elle sert à essayer les trois modèles (BiLSTM, DistilBERT, LAYA) sur sa machine, sans clé ni cluster. **Elle n'est pas déployée** : l'API en service est dans [`../api/`](../api/).

| Fichier | Rôle |
|---|---|
| `main_local.py` | Routes `/predire` et `/sante`, sert l'interface `front/index.html` |
| `modeles.py` | Chargement des trois modèles depuis `models/` et prédiction (avec lecture par fenêtres des textes longs) |
| `preprocess.py` | Copie du prétraitement des notebooks (anonymisation, nettoyage, normalisation) : à régénérer si les notebooks changent |
| `export_seuils.py` | Recalcule `models/seuils.json` depuis les prédictions enregistrées |

Lancer, depuis la racine du dépôt : `uvicorn api_locale.main_local:app --port 8000`, puis http://127.0.0.1:8000/docs.

Les scripts d'attaque et de défense du dossier [`../attack/`](../attack/) utilisent ces modules pour mesurer les modèles en local.
