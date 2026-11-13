# Digital Social Score : API de détection de toxicité

API qui note la toxicité d'un commentaire de **0 à 100**, avec anonymisation RGPD, déployée sur Google Cloud (Kubernetes). Projet de l'équipe NOUDEGBE Situ, OUEDRAOGO Eliana, CAKPOSSA Enzo (TP « API Digital Social Score », ESIGELEC).

## Où lire

**`DOCUMENTATION.pdf`** (même contenu que `DOCUMENTATION.md`, images incluses) : c'est le livrable. Il suit les étapes 1 à 7 du TP, justifie chaque choix et indique ce qui reste faible. Il contient en annexe la grille de tests (A) et le rapport de charge (B).

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
Réponse : `score` (0 à 100), `labels` (probabilité de chacun des 6 labels), `seuils`, `labels_detectes`, `toxique`, `model_version`, ainsi que `texte_anonymise` et `texte_nettoye` (ce que le serveur a fait du texte : le front les affiche et ne garde que le texte anonymisé dans son historique). Codes d'erreur : 401 (clé absente ou fausse), 422 (texte vide ou de plus de 5 000 caractères).

**3. Avec la documentation interactive** : `https://<adresse>/docs` (la route `/score` s'y teste avec la clé dans l'en-tête `X-API-Key`).

Si l'API ne répond pas : le cluster est parfois mis en pause pour économiser le crédit Google Cloud. Prévenir l'équipe.

## Contenu du dépôt

| Dossier ou fichier | Contenu |
|---|---|
| `DOCUMENTATION.md` / `.pdf` | Documentation complète, étapes 1 à 7, annexes |
| `front/index.html` | Interface de démonstration (un seul fichier, rien à installer) |
| `notebooks/` | Anonymisation, nettoyage, entraînement des 3 modèles (BiLSTM, DistilBERT, LAYA) |
| `api/` | API locale de développement (route `/predire`). Le code de l'API **déployée** (route `/score`, manifestes Kubernetes, scripts Google Cloud) est sur la branche `Enzo`, avec le CORS et les champs `texte_anonymise` / `texte_nettoye` sur la branche `cors` |
| `loadtest/` | Tests de charge Locust, rapport et courbes |
| `supervision/` | Grille de tests, plan de supervision, tableau de bord Grafana importable (`grafana_dashboard.json`), installation de Prometheus et Grafana |
| `images/` | Schéma d'architecture cloud et son script |
| `outils/` | Export de la documentation en PDF |

## Aller plus loin (optionnel)

- **Refaire l'entraînement** : voir la section « Reproduire » de la documentation. Compter environ 1 h pour DistilBERT et 2 h pour LAYA, sur un Mac M3 ; les modèles ne sont pas dans le dépôt (trop lourds) et les données brutes viennent du *Toxic Comment Classification Dataset* (Kaggle).
- **API locale** : `pip install -r requirements.txt` (Python 3.12), puis `uvicorn api.main:app --port 8000` après l'entraînement, et `front/index.html` en choisissant « API locale ».
- **Tests de charge** : `locust -f loadtest/locustfile.py,loadtest/montee.py --host https://<adresse>` avec la clé dans la variable d'environnement `API_KEY` (voir l'Annexe B). Ces tests consomment du crédit Google Cloud : à ne pas lancer sans prévenir l'équipe.
- **Régénérer le PDF** : `python outils/exporter_documentation.py` (nécessite Chrome ou Brave).

## Limites connues

Elles sont détaillées dans la documentation : pas de limitation de débit, documentation `/docs` publique, une clé d'API partagée, trafic non chiffré entre le load balancer et les pods, latence du P95 non mesurable au-delà de 1 s dans Prometheus, et un compte Google Cloud limité (le remplacement d'un pod peut prendre plusieurs minutes).
