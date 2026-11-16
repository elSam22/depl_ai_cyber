# Étape 6 : sécurité et supervision — plan

Ce que demande le TP : observer la stabilité en cas de stress ; tester la supervision **Prometheus / Grafana** ; analyser les logs et les comportements anormaux ; simuler une **panne ou une attaque** et évaluer la continuité du service. Livrables : tableau de bord / captures de supervision, grille de tests (voir [GRILLE_TESTS.md](GRILLE_TESTS.md)).

## Où on en est
- **Déjà fait :** stress et failover (étape 5), tests de sécurité S1 à S4 sur le cluster, grille de tests commencée.
- **Préparé, pas lancé :** [loadtest/attaque.py](../loadtest/attaque.py) (rafale d'attaquants + utilisateurs légitimes).
- **Fait (12 novembre) :** Prometheus et Grafana installés, `/metrics` déployé par Enzo (port 9090, non public), PodMonitor appliqué, 2 pods collectés, captures d'une montée progressive (voir [GRILLE_TESTS.md](GRILLE_TESTS.md), tests SU1 à SU8).
- **Fait aussi :** panne brutale (F2, F3, F3b), attaque à faible intensité (S7, S8), analyse des logs (S5), bogue de clé à accent (S2b).
- **Pas fait :** alertes créées dans Prometheus, tableau de bord Grafana construit à la main, perte d'une machine entière (F4), correctifs côté API (clé à accent, PodMonitor dans le déploiement, intervalles de latence, PodDisruptionBudget, limitation de débit).

## Décisions à prendre (avec Enzo, qui déploie)

| Décision | Options | Recommandation |
|---|---|---|
| **Comment exposer les métriques de l'API** | (a) ajouter `prometheus-fastapi-instrumentator` à l'API (2 lignes + une dépendance, puis redéploiement) ; (b) s'en passer et lire les métriques du load balancer Google dans Cloud Monitoring | (a) : donne requêtes/s, erreurs et latence par route. Protéger `/metrics` : par défaut il serait public via l'Ingress. |
| **Où faire tourner Prometheus et Grafana** | (a) Helm `kube-prometheus-stack` dans le cluster ; (b) Google Managed Service for Prometheus + Grafana ; (c) Cloud Monitoring seul | À trancher. Le TP cite Prometheus et Grafana : éviter (c). Sur Autopilot, certains composants (ex. `node-exporter`) peuvent être refusés : **à vérifier**. |
| **Coût** | Autopilot facture les ressources demandées par chaque pod, supervision comprise | Estimer avant d'installer ; mettre la supervision en pause avec le reste (`gke_pause.sh`). |

## Fait : Prometheus et Grafana installés (12 novembre)
Namespace `monitoring`, release Helm `monitoring`. Réglages retenus et pourquoi : voir [INSTALLER_PROMETHEUS_GRAFANA.md](INSTALLER_PROMETHEUS_GRAFANA.md). Grafana n'est joignable que par `port-forward` (rien d'exposé sur Internet). Alertmanager retiré (aucun canal de notification configuré, et le cluster manquait de mémoire).

## Fait : `/metrics` côté API
Déployé par Enzo : métriques servies sur un **port séparé (9090)**, donc pas publiques (le Service et l'Ingress n'exposent que 8080). Un `PodMonitor` (`monitoring/dss-api`, label `release: monitoring`) a dû être appliqué **à la main** : le script de déploiement ne l'applique pas. **À corriger avec Enzo :** (1) intégrer le PodMonitor au déploiement ; (2) élargir les intervalles de l'histogramme de latence (par défaut limités à 1 s, la courbe P95 reste bloquée à 1 s) ; (3) l'alerte « P95 > 2 s » ne peut pas fonctionner tant que (2) n'est pas fait.

## À mesurer (tableau de bord)
Requêtes/s, taux d'erreur (4xx, 5xx), latence P50 / P95 / P99, CPU par pod, nombre de pods, état de l'autoscaler. **Alertes proposées :** P95 > 2 s pendant 2 min ; taux d'erreur > 5 % ; moins de 2 pods prêts ; CPU > 90 % pendant 5 min. Les seuils viennent des mesures de l'étape 5 (2 s = notre critère de stress).

## Ordre de travail
1. Décider outil, emplacement et coût (avec Enzo).
2. Instrumenter l'API (`/metrics`), Enzo redéploie (`deploy_gke.sh`).
3. Installer Prometheus et Grafana ; construire le tableau de bord et les alertes.
4. **Rejouer la montée progressive** avec le tableau de bord ouvert ; captures pour le rapport.
5. **Panne** : arrêt brutal d'un pod (`kubectl delete pod --grace-period=0 --force`, F2) et perte d'un pod avec 2 pods seulement (F3).
6. **Attaque** : lancer `loadtest/attaque.py` à faible intensité ; vérifier que les utilisateurs légitimes gardent leur P95 (S7) et noter l'absence de limitation de débit (S8).
7. **Analyse des logs** dans Cloud Logging : lignes `score=… longueur=… duree_ms=…`, erreurs 502 observées pendant les tests, vérification qu'aucun texte n'y figure (S5).
8. Compléter [GRILLE_TESTS.md](GRILLE_TESTS.md), le rapport et la documentation.

## Points d'attention
- **Pas de limitation de débit** et **`/docs` public** : à signaler comme points faibles dans le rapport, même si on ne les corrige pas.
- Le journal de l'API ne contient **pas de hash de clé** : on ne pourra pas attribuer une attaque à une clé (voir registre RGPD, § 7.5 de la documentation).
- Ne jamais écrire la clé d'API dans un fichier du dépôt (dépôt public).
- Les tests d'attaque et de panne chargent le cluster partagé : prévenir l'équipe et le crédit avant de les lancer.
