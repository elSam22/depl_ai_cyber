# API Digital Social Score

API FastAPI qui renvoie un score de toxicité (0-100). Flux d'une requête :
clé API → validation → anonymisation → nettoyage → modèle → score. Le texte n'est jamais stocké.

| Fichier | Rôle |
|---|---|
| `main.py` | Routes `/health` et `/score`, clé API, validation, logs sans texte |
| `preprocessing.py` | Anonymisation + nettoyage : **source unique**, aussi importée par les notebooks |
| `scorer.py` | Chargement du modèle (factice, BiLSTM ou DistilBERT) d'après `model/meta.json` |
| `export_model.py` | Copie `models/<type>` dans `api/model/` et écrit `meta.json` |
| `Dockerfile` | Image de l'API (logs d'accès désactivés : pas d'IP client journalisée) |
| `k8s/` | Manifests Kubernetes : Deployment (2 pods, sondes), Service, Ingress HTTPS, HPA |
| `deploy/` | Scripts GCP : mise en place du cluster, déploiement, pause (coûts) |
| `tests/` | Tests pytest (API, prétraitement, parité) + `locustfile.py` (charge) |

## 1. Lancer en local (modèle factice tant que `model/meta.json` n'existe pas)

```bash
cd api
pip install -r requirements-dev.txt --extra-index-url https://download.pytorch.org/whl/cpu
pytest                                     # 15 tests (+ parité si data/clean existe)
API_KEY=test123 uvicorn main:app --reload --port 8000
```

## 2. Brancher le vrai modèle (après notebooks/train.ipynb)

```bash
python api/export_model.py --type distilbert     # ou --type bilstm
```

Les notebooks doivent importer `api/preprocessing.py` (et ne plus définir leurs propres fonctions),
sinon le test de parité échoue et l'API refuse un modèle dont la version de prétraitement diffère.

## 3. Tester l'image Docker en local

```bash
docker build -t dss-api api
docker run --rm -p 8080:8080 -e API_KEY=test123 dss-api
curl localhost:8080/health
```

## 4. Déployer sur GKE (Kubernetes Autopilot, région Paris)

Outils (une fois, dans le Codespace) :

```bash
curl -sSL https://sdk.cloud.google.com | bash -s -- --disable-prompts
source ~/google-cloud-sdk/path.bash.inc
gcloud components install kubectl gke-gcloud-auth-plugin --quiet
gcloud auth login
```

Avant tout : console GCP → Facturation → Budgets et alertes → créer une alerte (ex. 50 % et 90 % des crédits).

```bash
PROJECT_ID=<id-du-projet> bash api/deploy/gke_setup.sh     # une seule fois (~10 min)
PROJECT_ID=<id-du-projet> bash api/deploy/deploy_gke.sh    # à chaque nouvelle version
bash api/deploy/gke_pause.sh stop                          # en fin de séance : 0 pod, coûts quasi nuls
bash api/deploy/gke_pause.sh start                         # reprise
```
