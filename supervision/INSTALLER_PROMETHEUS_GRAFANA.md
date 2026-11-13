# Installer Prometheus et Grafana sur le cluster (depuis Cloud Shell)

À lancer **dans Cloud Shell**, connecté au cluster (`gcloud container clusters get-credentials dss-cluster --region europe-west9`). Ces commandes n'ont **pas été testées** sur ce cluster : GKE Autopilot refuse certains composants, il faudra peut-être ajuster. Elles n'installent rien dans le namespace de l'API (`default`) et ne modifient pas ses pods.

**Prévenir Enzo avant** : la supervision consomme du crédit (les pods de Prometheus et Grafana s'ajoutent à ceux de l'API).

## 1. Vérifications

```bash
helm version                  # Helm 3 est déjà installé dans Cloud Shell
kubectl get pods              # l'API tourne : 2 pods dss-api au minimum
kubectl get ns                # le namespace « monitoring » ne doit pas exister
```

## 2. Installation

Chart `kube-prometheus-stack` : Prometheus, Grafana, Alertmanager, kube-state-metrics et des tableaux de bord Kubernetes prêts à l'emploi.

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --timeout 20m \
  --set prometheusOperator.admissionWebhooks.enabled=false --set prometheusOperator.tls.enabled=false \
  --set nodeExporter.enabled=false \
  --set kubeEtcd.enabled=false --set kubeScheduler.enabled=false \
  --set kubeControllerManager.enabled=false --set kubeProxy.enabled=false \
  --set coreDns.enabled=false \
  --set prometheus.prometheusSpec.retention=2d \
  --set prometheus.prometheusSpec.resources.requests.cpu=250m \
  --set prometheus.prometheusSpec.resources.requests.memory=512Mi \
  --set grafana.adminPassword="$(openssl rand -hex 12)"
```

Pourquoi ces options (à garder pour la justification) :
- `admissionWebhooks.enabled=false` et `tls.enabled=false` : le job de configuration des webhooks n'a jamais terminé sur Autopilot (son compte de service était supprimé par Helm après le délai). On perd seulement la validation de syntaxe des règles Prometheus à leur création. **C'est la configuration finale qui a fonctionné le 12 novembre (release `deployed`, révision 2).**
- `nodeExporter.enabled=false` : il demande un accès aux machines que GKE Autopilot refuse (à vérifier).
- `kubeEtcd`, `kubeScheduler`, `kubeControllerManager`, `kubeProxy`, `coreDns` à `false` : ces composants sont gérés par Google et ne sont pas accessibles à Prometheus, ils ne produiraient que des alertes d'erreur.
- `retention=2d` et ressources réduites : limiter le crédit consommé.
- Mot de passe Grafana aléatoire (voir étape 4) : pas de mot de passe par défaut.
- **Aucun accès public** : pas d'Ingress, Grafana n'est joignable que par `port-forward` (étape 4).

Attendre que tout soit prêt (quelques minutes, tous les pods en `Running`, `Ctrl+C` pour quitter) :

```bash
kubectl -n monitoring get pods -w
```

**Erreur « failed post-install … admission-patch not ready … context deadline exceeded » (rencontrée le 12 novembre).** Sur Autopilot, Google doit d'abord préparer de nouvelles machines pour chaque pod ; le premier install dépasse le délai de 5 minutes de Helm. Les ressources sont quand même créées. Vérifier avec `kubectl -n monitoring get pods,jobs`, attendre que les pods soient `Running` et le job `Completed`, puis finir proprement (garde les mêmes réglages et le même mot de passe) :

```bash
helm upgrade monitoring prometheus-community/kube-prometheus-stack -n monitoring --reuse-values --timeout 20m
helm status monitoring -n monitoring      # doit afficher « STATUS: deployed »
```

Si un pod reste en `Pending` ou en erreur, **copier la sortie** de `kubectl -n monitoring describe pod <nom>` : c'est la limite d'Autopilot ou le quota du compte.

## 3. Récupérer le mot de passe Grafana

```bash
kubectl -n monitoring get secret monitoring-grafana -o jsonpath="{.data.admin-password}" | base64 -d; echo
```

Identifiant : `admin`. **Ne pas écrire ce mot de passe dans le dépôt.**

## 4. Ouvrir Grafana

```bash
kubectl -n monitoring port-forward svc/monitoring-grafana 8080:80
```

Puis, dans Cloud Shell, bouton **Aperçu sur le Web** (Web Preview) → **Prévisualiser sur le port 8080**.

## 5. Premiers tableaux de bord

Menu **Dashboards** :
- **Kubernetes / Compute Resources / Namespace (Pods)** → namespace `default` : CPU et mémoire de chaque pod `dss-api`.
- **Kubernetes / Compute Resources / Workload** → `dss-api` : vue globale du déploiement.

Si les panneaux de CPU sont vides, Prometheus n'arrive pas à lire les métriques des conteneurs sur Autopilot : le noter, on passera par les métriques de Google Cloud.

## 6. Vérifier le nombre de pods et l'autoscaler

Dans Grafana → **Explore** → source Prometheus, requêtes :
- pods prêts : `kube_deployment_status_replicas_ready{deployment="dss-api"}`
- réplicas voulus par l'autoscaler : `kube_horizontalpodautoscaler_status_desired_replicas{horizontalpodautoscaler="dss-api"}`
- CPU par pod : `sum(rate(container_cpu_usage_seconds_total{namespace="default",pod=~"dss-api.*"}[1m])) by (pod)`

## 7. Arrêter pour économiser le crédit

```bash
helm uninstall monitoring -n monitoring
kubectl delete namespace monitoring
```

(Les CRDs de Prometheus restent installées : sans effet sur le coût.)

## Ce qui a été fait ensuite (12 novembre), et pourquoi

1. **PodMonitor pour l'API** (le script de déploiement ne l'applique pas) : ressource `PodMonitor` `dss-api` dans `monitoring`, label `release: monitoring` (sans lui, Prometheus l'ignore), qui cible les pods `app: dss-api` du namespace `default`, port nommé `metrics`, chemin `/metrics`. Contrôle : Status → Targets, 2 cibles `UP`.
2. **Grafana en version 10.4.2** (`--set grafana.image.tag=10.4.2`) : en version 13.3.1, l'interface ne se chargeait pas à travers l'aperçu web de Cloud Shell (`ChunkLoadError`, même fichier sur deux navigateurs et deux ports).
3. **Stratégie « Recreate »** (`--set grafana.deploymentStrategy.type=Recreate`) : la mise à jour progressive exigeait de la place pour un 2e pod, alors que les deux machines étaient pleines et que Google n'en fournissait plus dans la zone.
4. **Alertmanager retiré** (`--set alertmanager.enabled=false`) : aucun canal de notification n'est configuré et il occupait de la mémoire.
5. **Adresse de l'aperçu déclarée à Grafana** (`--set grafana.env.GF_SERVER_ROOT_URL="https://<hôte de l'aperçu>" --set grafana.env.GF_SECURITY_CSRF_TRUSTED_ORIGINS="<hôte>"`) : sans cela, la connexion échouait avec « origin not allowed ». L'hôte change si Cloud Shell est recréé.
6. **Pas d'exposition publique de Grafana** : essayée (Ingress + certificat géré), abandonnée puis supprimée (Ingress, certificat, adresse IP réservée) : un service de plus sur Internet n'était pas justifié.

**Limite connue :** les tableaux de bord Kubernetes prêts à l'emploi n'affichent pas l'usage CPU/mémoire (GKE Autopilot ne laisse pas Prometheus lire le kubelet). Requêtes de remplacement, issues des métriques de l'API : `sum(rate(process_cpu_seconds_total{namespace="default",pod=~"dss-api.*"}[1m])) by (pod)` et `sum(process_resident_memory_bytes{namespace="default",pod=~"dss-api.*"}) by (pod)`.
