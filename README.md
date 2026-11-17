# Digital Social Score : API de détection de toxicité

[![Sécurité et tests](https://github.com/elSam22/depl_ai_cyber/actions/workflows/securite.yml/badge.svg?branch=ci)](https://github.com/elSam22/depl_ai_cyber/actions/workflows/securite.yml)

API qui note la toxicité d'un commentaire de **0 à 100**. Elle anonymise le texte (RGPD) avant le modèle DistilBERT. Elle est déployée sur Google Kubernetes Engine (Paris) et protégée contre les attaques étudiées au TP2.

**Équipe** : CAKPOSSA Jean-Philippe, OUEDRAOGO Eliana, NOUDEGBE Situ. Module « Déploiement de solutions IA et cybersécurité », ESIGELEC, novembre 2026.

## Livrables

Ils sont tous dans [`livrables/`](livrables/). Il y a un document par TP, en PDF, avec les images intégrées. Chaque document suit les étapes de l'énoncé, puis reprend ses livrables et ses critères d'évaluation.

| Document | Contenu |
|---|---|
| [**TP1_LIVRABLE.pdf**](livrables/TP1_LIVRABLE.pdf) ([source Markdown](livrables/TP1_LIVRABLE.md)) | Étapes 1 à 7 : anonymisation, 3 modèles comparés, API, déploiement GKE, tests de charge, sécurité et supervision, architecture. En annexe : la grille de tests, le rapport de charge et le registre RGPD |
| [**TP2_LIVRABLE.pdf**](livrables/TP2_LIVRABLE.pdf) ([source Markdown](livrables/TP2_LIVRABLE.md)) | Étapes 1 à 5 : attaque par évasion, défense mesurée (en local et sur l'API déployée), conformité IA Act, pipeline DevSecOps, analyse critique |
| [REGISTRE_RGPD.md](livrables/REGISTRE_RGPD.md) | Registre des traitements, version 1.1 (également reproduit dans l'annexe C du TP1) |
| [model_card.json](model_card.json) | Fiche du modèle (IA Act). Elle reste à la racine parce que la pipeline la contrôle à chaque modification |

## Résultats principaux

- **Modèle** : sur 10 000 lignes du test officiel, DistilBERT atteint une ROC-AUC de **0,977**. Il est comparé au BiLSTM (0,916) et à LAYA (0,969), avec les mêmes données pour les trois.
- **RGPD** : le texte est anonymisé avant le modèle (regex et NER spaCy). Il n'est jamais enregistré, et les journaux n'en contiennent pas. Nous l'avons vérifié dans Cloud Logging.
- **Haute disponibilité** : l'autoscaler fait varier le nombre de pods de 2 à 5. Pendant une panne provoquée (suppression d'un pod), il n'y a eu **aucune erreur sur 1 192 requêtes**.
- **Robustesse à l'évasion** (mesurée par HTTP sur l'API déployée) : sans défense, 47 à 57 % des insultes déguisées passent. Avec la défense, il en passe **0 %** (homoglyphes, caractères invisibles) et **6 à 10 %** (leetspeak, lettres espacées).
- **Résistance au déni de service** : nous avons envoyé un flot de 201 requêtes par seconde sur `/score`. Un utilisateur légitime a obtenu **29 réponses sur 29**, avec un P95 multiplié par **2,3** (contre 76 lors de l'attaque du 16 novembre).
- **Pipeline DevSecOps** : 7 contrôles (secrets, code, configuration, image, IA Act, tests, dépendances) bloquent tout déploiement en cas d'échec.
  - On ne déploie que depuis la branche protégée `ci`.
  - Les actions GitHub sont figées par empreinte.
  - Google Cloud est joint sans clé stockée, par OIDC.
  - L'empreinte des poids du modèle est vérifiée avant chaque construction.

## Tester l'API déployée

**L'adresse et la clé d'API sont remises séparément** : ce dépôt est public, elles n'y figurent pas.

```bash
curl -X POST https://<adresse>/score \
  -H "Content-Type: application/json" -H "X-API-Key: <clé>" \
  -d '{"text":"You are a stupid idiot"}'
```

Réponse : `{"score":100,"toxique":true}`. Le score est arrondi à la dizaine ; probabilités et seuils ne sont pas renvoyés, pour gêner le contournement et le vol du modèle.

Codes renvoyés :

| Code | Cause |
|---|---|
| 401 | Clé absente ou fausse |
| 413 | Corps de plus de 40 Ko |
| 422 | Texte vide ou de plus de 5 000 caractères |
| 429 | Débit dépassé, réponse avec `Retry-After` |
| 503 | Pod saturé, réessayer une seconde plus tard |

**Interface graphique** : ouvrir [`front/index.html`](front/index.html) dans un navigateur, choisir « API distante », coller l'adresse et la clé. La clé n'est jamais enregistrée.

## Organisation du dépôt

```
livrables/      Livrables TP1 et TP2 (PDF + source Markdown), registre RGPD, images/ (schéma d'architecture)
notebooks/      TP1, étapes 1-2 : anonymisation, nettoyage, entraînement des 3 modèles
api/            API DÉPLOYÉE uniquement : main.py, protection.py, scorer.py, Dockerfile, k8s/, deploy/, tests/
api_locale/     API de développement (3 modèles, route /predire) : ce qui n'est pas déployé
front/          Interface de démonstration (un seul fichier HTML)
loadtest/       TP1, étape 5 : tests de charge Locust, rapport, courbes, résultats bruts
supervision/    TP1, étape 6 : Prometheus/Grafana, alertes, tableau de bord, registre des incidents
attack/         TP2 : scripts d'attaque et de défense, mesures sur l'API déployée, rapport technique
  inter_equipes/  outil d'attaque des API d'autres équipes (avec leur accord), leurs rapports et résultats
.github/        Pipeline DevSecOps (securite.yml) et mises à jour automatiques (Dependabot)
data/           Jeu de données public (Toxic Comment Classification, Kaggle)
cours/          Énoncés des TP et critères d'évaluation
outils/         Export des livrables en PDF, contrôle de mise en page, contrôle de la fiche modèle
```

**Branches** : `main` contient le code et les livrables. `ci` est la branche protégée que la pipeline déploie : on n'y entre que par une pull request dont les contrôles sont verts.

## Reproduire

- **Environnement** : Python 3.12, `pip install -r requirements.txt`.
- **Entraînement** : exécuter les notebooks dans l'ordre (`anonyme_2`, `clean_text`, `train`). Il faut environ 1 h pour DistilBERT sur un Mac M3. Les modèles ne sont pas dans le dépôt, à cause de leur taille.
- **API locale** : `uvicorn api_locale.main_local:app --port 8000`, puis http://127.0.0.1:8000.
- **Tests** : `pytest api/tests`.
- **Attaque rejouée sur l'API déployée** : `URL=https://<adresse> API_KEY=<clé> python -m attack.mesure_api_deployee`.
- **Régénérer un PDF** : `python outils/exporter_documentation.py livrables/TP2_LIVRABLE.md`. Il faut Chrome ou Brave.

Les tests de charge et d'attaque consomment du crédit Google Cloud. Ils ne visent que notre propre API.

## Limites connues

Elles sont détaillées et priorisées dans les livrables (TP1 § 10, TP2 § 9) :
- la limitation de débit s'applique par pod, sans pare-feu applicatif, car le quota du projet a refusé Cloud Armor ;
- une seule clé d'API est partagée ;
- les alertes s'affichent à l'écran, sans notification ;
- la défense contre le noyage réduit l'attaque mais ne l'élimine pas.
