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
- **Mêmes données pour les trois modèles (consigne du prof) :**
  - *entraînement commun* : `N_COMMUN` = 30 000 lignes tirées des 80 % de `train_clean.csv`, stratifiées sur la combinaison exacte des 6 labels (graine 42), identiques pour BiLSTM, DistilBERT et LAYA (qui n'est pas entraîné) ;
  - *validation* : les 20 % restants de `train_clean.csv` (graine 42). Elle sert à **choisir les seuils** (voir plus bas). BiLSTM et DistilBERT l'utilisent en entier, LAYA en utilise `N_VAL_LAYA` = 3 000 lignes (inférence lente) ;
  - *test officiel commun* : `N_TEST_COMMUN` = 10 000 lignes tirées (graine 42) de `data/clean/test_clean.csv` avec `data/test_labels.csv`, **les mêmes pour les trois modèles**, regardées une seule fois à la fin, sans aucun réglage dessus.
- **Lignes à -1 :** dans `test_labels.csv`, `-1` signifie « non évalué par Kaggle » (89 186 lignes sur 153 164). Elles sont retirées au chargement du test officiel, **avant** toute prédiction : il reste 63 978 lignes évaluées. Le tableau final donne les résultats validation et test côte à côte.
- **Multi-label :** 6 sorties sigmoïde, perte `BCEWithLogitsLoss` avec `pos_weight = négatifs / positifs` par label, calculé sur les données réellement vues par le modèle. Choix : les classes rares (`threat`, `identity_hate`, `severe_toxic`) sont sinon ignorées. Effet attendu : rappel élevé, précision plus faible au seuil 0,5.
- **Seuil :** le notebook donne les résultats au seuil fixe 0,5 **et** au seuil optimisé. Seuil optimisé = pour chaque label, le seuil (de 0,02 à 0,98) qui maximise le F1 sur la **validation** ; il est ensuite appliqué tel quel au test. Raison : `pos_weight` rend les probabilités trop hautes, le seuil 0,5 donne un rappel très élevé et une précision faible (BiLSTM mesuré : rappel 0,93, précision 0,29). La ROC-AUC ne dépend pas du seuil. Limite : les labels rares (`threat`) ont peu de positifs en validation, leur seuil est moins stable. Les seuils sont sauvegardés dans `models/seuils.json` (à réutiliser dans l'API pour le score 0-100).
- **Modèle 1, BiLSTM :** embedding 128, LSTM bidirectionnel 64 par sens, max-pooling sur la séquence (padding ignoré), dropout 0,3, vocabulaire 30 000 mots (construit sur le train uniquement), longueur max 200, batch 128, entraîné sur les 30 000 lignes communes (vocabulaire construit sur ces lignes). Non imposés par la consigne, donc choisis : Adam lr 1e-3, 3 époques.
- **Modèle 2, DistilBERT :** `distilbert-base-uncased`, longueur max 128, 2 époques, lr 2e-5, batch 16, AdamW (weight decay 0,01, échauffement 10 %). Entraîné sur les 30 000 lignes communes (stratifiées). Raison de cette taille : temps d'entraînement raisonnable sur un Mac M3. Si `models/distilbert` existe déjà, le notebook le recharge au lieu de le réentraîner (`REENTRAINER_BERT`).
- **Modèle 3, LAYA** (Convai Innovations, Apache 2.0, non autorégressif, backbone ModernBERT-large 421 M, `pip install laya`, checkpoint `convaiinnovations/laya`) : une question oui/non (`noul`) par label, la probabilité de « oui » sert de score. **Non entraîné (zéro-shot), décision prise avec le groupe**, car les deux voies d'entraînement sont irréalistes sur un Mac M3 16 Go :
  - fine-tuning complet (RLCD) : 4 à 5 h sur 2 GPU T4 pour 30 000 questions d'après la doc, ici 6 questions par commentaire, script prévu pour un autre format de données ;
  - `agent.fit` (têtes apprises sur le lecteur gelé `vegaml` 0,8 B) : **mesuré à 7,6 s par ligne** d'entraînement et 1,8 s par prédiction, soit ~63 h pour 30 000 lignes ; sur 120 lignes, la tête n'était retenue que pour 3 labels sur 6.
  La documentation de LAYA indique que ses checkpoints de base sont proches du hasard hors de leur domaine (0,362 contre 0,318 pour le hasard sur leur benchmark) et sur-confiants : résultat à lire comme un **plancher**, à expliquer dans le rapport (LAYA est évalué sur le même test que les autres mais n'a vu aucune donnée d'entraînement). Inférence ~0,2 à 0,4 s par commentaire sur MPS (`predict_batch` n'aide pas) : environ 1 h pour 3 000 lignes de validation + 10 000 lignes de test.
- **Mesures :** précision, rappel, F1 et ROC-AUC par label ; temps d'entraînement ; temps d'inférence sur le jeu de test (total et par commentaire).
- **Sauvegarde :** `models/bilstm/` (poids + vocabulaire), `models/distilbert/` (modèle + tokenizer + `temps_train.json`), `models/resultats.csv`, `models/resultats_par_label.csv`, `models/seuils.json`.

## API locale (test des modèles)

Dossier `api/` : `main.py` (routes FastAPI), `modeles.py` (chargement BiLSTM / DistilBERT / LAYA), `preprocess.py` (copie du code d'anonymisation et de nettoyage des notebooks : à régénérer si on les modifie), `export_seuils.py` (recalcule `models/seuils.json` depuis les prédictions enregistrées).

- Lancer (depuis la racine) : `.venv/bin/uvicorn api.main:app --port 8000` ; interface de test : http://127.0.0.1:8000/docs.
- `GET /sante` : état et modèles disponibles. `POST /predire` : `{"texte": "...", "modele": "bilstm" | "distilbert" | "laya", "anonymiser": true}`.
- Chaîne : texte -> anonymisation (regex + NER, comme à l'entraînement) -> nettoyage -> modèle -> 6 probabilités -> seuils par label (`models/seuils.json`, sinon 0,5 avec avertissement).
- **Score 0-100** : score d'un label = **probabilité × 100**. Un label est « true » si sa probabilité ≥ son seuil. `score_global` = la **moyenne des scores des labels true** s'il y en a (un seul : son score), sinon le score du label `toxic` ; `toxique` = au moins un label true.
- **Modèle par défaut : DistilBERT** (meilleur ROC-AUC et meilleur F1 sur le test commun, inférence ~8 ms) ; BiLSTM et LAYA restent sélectionnables. Valeur par défaut de `modele` dans `api/main.py` et modèle coché au chargement dans `front/index.html`.
- RGPD : le texte reçu n'est ni enregistré ni écrit dans les logs. Entrée validée (1 à 5 000 caractères, modèle dans une liste fermée).
- DistilBERT et BiLSTM sont préchargés au démarrage ; LAYA (800 Mo, lent, ~0,3 s par texte) se charge à la première utilisation. Un modèle dont les fichiers manquent renvoie une erreur 503 explicite.
## Front de démonstration

`front/index.html` : page unique (HTML/CSS/JS, rien à installer), servie par l'API sur http://127.0.0.1:8000/. Choix « API locale » (défaut) ou « API distante » (URL + clé, envoyée dans l'en-tête `X-API-Key`, jamais stockée ; CORS ouvert côté API). Saisie du commentaire + choix du modèle (grisé si indisponible) -> animation du prétraitement (original -> anonymisation en balises -> nettoyage, via le champ `etapes` de la réponse) -> jauge animée 0 -> score (vert < 30, orange 30-60, rouge > 60) -> barres de probabilité par label avec leur seuil. Deux versions, choisies par l'interrupteur en haut : **Classique** et **Pipeline** (message -> enveloppe -> algorithme -> réseau de neurones -> résultat, ~8-10 s, « Passer l'animation », mise en scène des vraies données, pas un suivi en direct). Bouton **Stop** (annule la requête côté navigateur ; le serveur finit son calcul). Durées affichées (prétraitement = anonymisation + nettoyage, réflexion du modèle, total) : champs `temps_pretraitement_ms`, `temps_modele_ms`, `temps_ms` de `/predire` et `etapes.temps_anonymisation_ms` / `temps_nettoyage_ms`. **Historique** (sessionStorage de l'onglet) : seul le texte **anonymisé** est conservé (RGPD) ; un clic ouvre le détail complet, modifiable et ré-analysable. Liste d'exemples dans l'onglet « Commentaires à tester ». Si on modifie `api/preprocess.py`, `pretraiter_detail` doit rester cohérent avec `pretraiter`.

## Étape 5 : test de charge (faite)

Dossier `loadtest/` : `locustfile.py` (POST /score, 1 000 textes de `test_clean.csv`, clé dans la variable d'environnement `API_KEY`, journal par requête si `LOG_REQUETES` est défini), `montee.py` (profil 1 -> 10 -> 50 -> 100 utilisateurs sur 5 min), `failover.py` (5 utilisateurs pendant 4 min), `stress.py` (+10 utilisateurs/20 s jusqu'à P95 > 2 s pendant 10 s), `report.py` (tableau par palier + graphique), `RAPPORT.md` (méthode, résultats, courbes, limites, améliorations), `images/`, `results/` (CSV). Cible : l'API d'Enzo sur GKE (2 à 5 pods), pas l'API locale ; les mesures incluent donc le réseau.
- Relancer : `API_KEY=... LOG_REQUETES=loadtest/results/montee_requetes.csv .venv/bin/locust -f loadtest/locustfile.py,loadtest/montee.py --host https://<domaine>.sslip.io --web-host 127.0.0.1 --csv loadtest/results/montee` (interface http://localhost:8089, cliquer sur Start), puis `.venv/bin/python loadtest/report.py montee`. Failover : `failover.py` à la place de `montee.py`, supprimer un pod (`kubectl delete $(kubectl get pods -o name | head -1); date -u +%T`), puis `report.py failover <HH:MM:SS UTC>`.
- Résultats : stress : rupture (P95 > 2 s) à 20 utilisateurs en 33 s, 0 erreur ; le débit plafonne vers 8 requêtes/s avec 2 pods (exécution 1), jusqu'à 17-20 avec l'autoscaler (exécution 2) ; latence moyenne > 2 s dès 50 utilisateurs ; < 0,2 % d'erreurs ; autoscaler : un pod neuf met ~5,5 min à être prêt (Autopilot prépare une machine) ; failover : 0 erreur sur 1 192 requêtes (suppression propre d'un pod, avec 5 pods prêts, observée 59 s). Résumé dans `DOCUMENTATION.md` § 6.
- Les percentiles du CSV de Locust sont cumulés depuis le début : ne pas les utiliser par palier.
- Dépôt public : ne jamais mettre l'URL complète avec la clé, ni la clé, dans un fichier.

- Registre RGPD fusionné (traitement du jeu de données + API en service) dans `DOCUMENTATION.md` § 7 ; copie d'origine d'Eliana corrigée : `REGISTRE_RGPD.md`.

Étape 7 (schéma d'architecture) : `images/architecture_cloud.png`, généré par `images/architecture_cloud.py`, avec texte explicatif, flux et zero trust dans `DOCUMENTATION.md` § 5.2 ; exemples de requêtes et réponses réels (API déployée) au § 5.3 ; correspondance avec les livrables du TP au § 8.

## Étape 6 : sécurité et supervision (préparée, pas commencée)

Dossier `supervision/` : `PLAN.md` (décisions à prendre avec Enzo, ordre de travail, alertes proposées), `GRILLE_TESTS.md` (livrable : tests de sécurité S1-S4 vérifiés sur le cluster, stress et failover remplis, panne brutale et attaque à faire). `loadtest/attaque.py` : rafale d'attaquants (sans clé, mauvaise clé, texte trop long, JSON invalide) + utilisateurs légitimes ; **non lancé**, prévenir l'équipe avant. Constats : `/docs` est public, pas de limitation de débit, l'API déployée n'expose pas de `/metrics`.
- Pas encore fait : Prometheus/Grafana, tests de panne brutale et d'attaque, analyse des logs, schéma d'architecture cloud (étape 7).

## Résultats

Cette section est écrite automatiquement par la dernière cellule de `notebooks/train.ipynb`.

<!-- RESULTATS:DEBUT -->

Macro-moyenne sur les 6 labels. Entraînement : mêmes 30000 lignes (LAYA : zéro-shot). **val** = 20 % de train ; **test** = 10000 lignes du test officiel Kaggle (sans les -1), les mêmes pour les trois modèles. Seuil optimisé = seuil par label maximisant le F1 sur la validation.

| modèle | lignes d'entraînement | entraînement (s) | ROC-AUC (val) | F1 (val, seuil optimisé) | inférence val (s) | lignes (val) | ROC-AUC (test) | précision (test, seuil 0,5) | rappel (test, seuil 0,5) | F1 (test, seuil 0,5) | précision (test, seuil optimisé) | rappel (test, seuil optimisé) | F1 (test, seuil optimisé) | inférence test (s) | ms/commentaire (test) | lignes (test) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BiLSTM | 3e+04 | 157.4 | 0.9478 | 0.4431 | 4.178 | 3.192e+04 | 0.9164 | 0.1444 | 0.867 | 0.2312 | 0.3011 | 0.4808 | 0.3579 | 1.314 | 0.1314 | 1e+04 |
| DistilBERT | 3e+04 | 3860 | 0.985 | 0.6155 | 410.1 | 3.192e+04 | 0.9771 | 0.1971 | 0.9794 | 0.3078 | 0.4932 | 0.6927 | 0.5577 | 81.03 | 8.103 | 1e+04 |
| LAYA (zéro-shot) | 0 | 0 | 0.9646 | 0.5767 | 2192 | 3000 | 0.9686 | 0.2375 | 0.8971 | 0.3283 | 0.3659 | 0.7403 | 0.4756 | 7006 | 700.6 | 1e+04 |

<!-- RESULTATS:FIN -->
