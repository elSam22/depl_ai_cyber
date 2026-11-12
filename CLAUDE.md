# Projet « Digital Social Score » (TP ESIGELEC)

API qui détecte la toxicité d'un texte et renvoie un score de 0 à 100, avec anonymisation RGPD. Énoncé : `cours/TP1_Digital_Social_Score.pdf`.
Jeu de données : *Toxic Comment Classification Dataset* (`comment_text` + 6 labels : toxic, severe_toxic, obscene, threat, insult, identity_hate).

## Chaîne de traitement

| Étape | Notebook | Entrée | Sortie |
|---|---|---|---|
| 1. Anonymisation (regex + NER spaCy) | `notebooks/anonyme_2.ipynb` | `data/train.csv`, `data/test.csv` | `data/anonymise/*_anonyme_2.csv` |
| 1b. Nettoyage (minuscules, emojis, ponctuation) | `notebooks/clean_text.ipynb` | `data/anonymise/` | `data/clean/train_clean.csv`, `test_clean.csv` |
| 2. Entraînement des modèles | `notebooks/train.ipynb` | `data/clean/train_clean.csv` | `models/` (non commité) |

Documentation de l'anonymisation et registre de traitement : `DOCUMENTATION.md`.

## Conventions

- Environnement : `.venv` (Python 3.12) ; kernel `.venv` dans VS Code. Code commenté en français.
- Les balises d'anonymisation sont `xxx_tag` (le `_` est conservé par le nettoyage). Pas de balise pour les lieux.
- Ne pas committer `data/anonymise/`, `data/clean/`, `models/` (voir `.gitignore`).
- Machine d'entraînement : Mac M3, 16 Go. PyTorch sur `mps` (repli CPU), `PYTORCH_ENABLE_MPS_FALLBACK=1`, tout en float32.

## Étape 2 : choix d'entraînement

- **Données :** `data/clean/train_clean.csv` (et non `data/train_clean.csv` : les fichiers générés sont rangés dans des dossiers dédiés).
- **Split :** 80/20, graine 42, mêmes indices pour tous les modèles (le jeu de test est donc identique).
- **Multi-label :** 6 sorties sigmoïde, perte `BCEWithLogitsLoss` avec `pos_weight = négatifs / positifs` par label, calculé sur les données réellement vues par le modèle. Choix : les classes rares (`threat`, `identity_hate`, `severe_toxic`) sont sinon ignorées. Effet attendu : rappel élevé, précision plus faible au seuil 0,5.
- **Seuil :** 0,5 pour précision / rappel / F1 ; la ROC-AUC ne dépend pas du seuil.
- **Modèle 1, BiLSTM :** embedding 128, LSTM bidirectionnel 64 par sens, max-pooling sur la séquence (padding ignoré), dropout 0,3, vocabulaire 30 000 mots (construit sur le train uniquement), longueur max 200, batch 128, jeu complet. Non imposés par la consigne, donc choisis : Adam lr 1e-3, 3 époques.
- **Modèle 2, DistilBERT :** `distilbert-base-uncased`, longueur max 128, 2 époques, lr 2e-5, batch 16, AdamW (weight decay 0,01, échauffement 10 %). Entraîné sur 30 000 lignes tirées du train, **stratifiées** sur la combinaison exacte des 6 labels (combinaisons de moins de 10 exemples regroupées). Raison : temps d'entraînement raisonnable sur un Mac M3. Évalué sur le même jeu de test complet que les autres.
- **Modèle 3, LAYA** (Convai Innovations, Apache 2.0, non autorégressif, backbone ModernBERT-large 421 M, `pip install laya`, checkpoint `convaiinnovations/laya`) : une question oui/non (`noul`) par label, la probabilité de « oui » sert de score. **Version zéro-shot** (API testée sur quelques commentaires) : la documentation de LAYA indique que les checkpoints de base sont proches du hasard sans fine-tuning (0,362 contre 0,318 pour le hasard sur leur benchmark) et sur-confiants. Résultat à lire comme un plancher ; le fine-tuning n'est pas fait. Inférence lente sur MPS (~0,2 s/commentaire ; `predict_batch` n'aide pas) : LAYA est évalué sur 2 000 lignes du jeu de test (`N_TEST_LAYA`), pas sur les ~32 000 ; le tableau indique le nombre de lignes évaluées.
- **Mesures :** précision, rappel, F1 et ROC-AUC par label ; temps d'entraînement ; temps d'inférence sur le jeu de test (total et par commentaire).
- **Sauvegarde :** `models/bilstm/` (poids + vocabulaire), `models/distilbert/` (modèle + tokenizer), `models/resultats.csv`.

## Résultats

Cette section est écrite automatiquement par la dernière cellule de `notebooks/train.ipynb`.

<!-- RESULTATS:DEBUT -->

Macro-moyenne sur les 6 labels, seuil 0.5. **val** = 20 % de train (graine 42) ; **test** = test officiel Kaggle sans les lignes à -1.

| modèle | entraînement (s) | précision (val) | rappel (val) | F1 (val) | ROC-AUC (val) | ms/commentaire (val) | lignes (val) | précision (test) | rappel (test) | F1 (test) | ROC-AUC (test) | ms/commentaire (test) | lignes (test) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BiLSTM | 88.09 | 0.2785 | 0.9402 | 0.3909 | 0.9765 | 0.08272 | 3.192e+04 | 0.1692 | 0.9483 | 0.2668 | 0.9645 | 0.08398 | 6.398e+04 |
| DistilBERT | 1710 | 0.3213 | 0.9545 | 0.4388 | 0.9853 | 9.081 | 3.192e+04 | 0.1989 | 0.9668 | 0.3095 | 0.9778 | 8.336 | 6.398e+04 |
| LAYA (zéro-shot) | 0 | 0.3663 | 0.8811 | 0.4307 | 0.9661 | 416.9 | 2000 | 0.2436 | 0.8999 | 0.3325 | 0.9714 | 417.3 | 2000 |

<!-- RESULTATS:FIN -->
