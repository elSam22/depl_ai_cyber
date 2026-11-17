# Digital Social Score : API de détection de toxicité

API qui note la toxicité d'un commentaire de **0 à 100**, avec anonymisation RGPD, déployée sur Google Cloud (Kubernetes). Projet de l'équipe NOUDEGBE Situ, OUEDRAOGO Eliana, CAKPOSSA Enzo (TP « API Digital Social Score », ESIGELEC).

## Où lire

Un livrable par TP, chacun en un seul document (Markdown et PDF, images incluses), structuré comme l'énoncé :
- **`TP1_LIVRABLE.pdf`** (source `TP1_LIVRABLE.md`) : étapes 1 à 7 du TP1, livrables et critères d'évaluation ; en annexe, la grille de tests (A) et le rapport de charge (B).
- **`TP2_LIVRABLE.pdf`** (source `TP2_LIVRABLE.md`) : étapes 1 à 5 du TP2 (attaque, défense, IA Act, pipeline DevSecOps), analyse critique et critères. Scripts d'attaque dans `attack/`, fiche du modèle dans `model_card.json`.

## Tester l'API déployée (aucune installation)

L'API tourne sur Google Cloud. **L'adresse et la clé d'API vous sont remises séparément** (elles ne sont pas dans ce dépôt, qui est public). Le modèle utilisé est celui du serveur (DistilBERT) : inutile de rien entraîner ni télécharger.

**1. Avec le front de démonstration** (le plus simple)
1. Ouvrir `front/index.html` dans un navigateur (double-clic) : le mode **« API distante (GKE) »** est déjà sélectionné.
2. (Si besoin, le choisir en haut.)
3. Coller l'**adresse** de l'API et la **clé** dans les deux champs, puis écrire un commentaire et cliquer sur **Analyser**.

La clé n'est jamais enregistrée : elle reste dans le champ le temps de la page. Le voyant à côté de « API locale » devient vert quand l'API répond.

**2. Avec `curl`**
```bash
curl -X POST https://<adresse>/score \
  -H "Content-Type: application/json" -H "X-API-Key: <clé>" \
  -d '{"text":"You are a stupid idiot"}'
```
Réponse volontairement pauvre, par exemple `{"score":100,"toxique":true}` : `score` de 0 à 100, **arrondi à la dizaine**, et `toxique` (au moins un des 6 labels dépasse son seuil). Les probabilités et les seuils ne sont pas renvoyés : ils aideraient à contourner le modèle ou à le cloner (voir la documentation, § 3.3). Codes d'erreur : 401 (clé absente ou fausse), 422 (texte vide ou de plus de 5 000 caractères).

**3. Documentation interactive : fermée en production** (`/docs` répond 404 depuis le 16 novembre, après une attaque : voir `TP1_LIVRABLE.md`, § 6.6). La route et le format sont décrits ci-dessus et dans la documentation (§ 3.3).

Si l'API ne répond pas : le cluster est parfois mis en pause pour économiser le crédit Google Cloud. Prévenir l'équipe.

## Contenu du dépôt

| Dossier ou fichier | Contenu |
|---|---|
| `TP1_LIVRABLE.md` / `.pdf` | Livrable du TP1 : étapes 1 à 7, critères, annexes |
| `TP2_LIVRABLE.md` / `.pdf` | Livrable du TP2 : étapes 1 à 5, analyse critique, critères |
| `attack/` | TP2 : scripts d'attaque et de défense, résultats (`attack/RAPPORT.md`) |
| `model_card.json` | TP2 : fiche du modèle (IA Act), contrôlée par la pipeline |
| `front/index.html` | Interface de démonstration (un seul fichier, rien à installer) |
| `notebooks/` | Anonymisation, nettoyage, entraînement des 3 modèles (BiLSTM, DistilBERT, LAYA) |
| `api/` | API locale de développement (route `/predire`). Le code de l'API **déployée** (route `/score`, manifestes Kubernetes, scripts Google Cloud) est sur la branche **`ci`** (c'est elle que la pipeline déploie ; elle contient le travail des branches `Enzo` et `Eliana`, le CORS et la pipeline). `main` ne contient que l'API locale |
| `loadtest/` | Tests de charge Locust, rapport et courbes |
| `supervision/` | Grille de tests, plan de supervision, tableau de bord Grafana importable (`grafana_dashboard.json`, avec une section de détection d'attaque), installation de Prometheus et Grafana, **registre des incidents** (`INCIDENTS.md`) et script d'analyse des journaux |
| `images/` | Schéma d'architecture cloud et son script |
| `outils/` | Export de la documentation en PDF |

## Aller plus loin (optionnel)

- **Refaire l'entraînement** : voir la section « Reproduire » de la documentation. Compter environ 1 h pour DistilBERT et 2 h pour LAYA, sur un Mac M3 ; les modèles ne sont pas dans le dépôt (trop lourds) et les données brutes viennent du *Toxic Comment Classification Dataset* (Kaggle).
- **API locale** : `pip install -r requirements.txt` (Python 3.12), puis `uvicorn api.main:app --port 8000` après l'entraînement, et `front/index.html` en choisissant « API locale ».
- **Tests de charge** : `locust -f loadtest/locustfile.py,loadtest/montee.py --host https://<adresse>` avec la clé dans la variable d'environnement `API_KEY` (voir l'Annexe B). Ces tests consomment du crédit Google Cloud : à ne pas lancer sans prévenir l'équipe.
- **Régénérer le PDF** : `python outils/exporter_documentation.py` (nécessite Chrome ou Brave).

## Limites connues

Elles sont détaillées dans les livrables : une limitation de débit **par pod** (pas globale : Cloud Armor refusé par le quota du projet, voir `TP2_LIVRABLE.md`, étape 3), une clé d'API partagée, trafic non chiffré entre le load balancer et les pods, pas d'Alertmanager (les alertes se lisent à l'écran), et un compte Google Cloud limité (le remplacement d'un pod peut prendre plusieurs minutes).
