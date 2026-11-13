# Grille de tests : sécurité, stress, failover

Livrable du TP (« Grille tests sécurité/stress/failover »). Cible : l'API déployée sur GKE. Date des essais : 12 novembre 2026.

Légende : **OK** = vérifié sur le cluster ; **code** = prévu dans le code (tests `pytest` de la branche Enzo), pas vérifié sur le cluster ; **à faire**.

## Sécurité

| ID | Test | Attendu | Résultat | État |
|---|---|---|---|---|
| S1 | `POST /score` sans clé | 401 | 401 | **OK** |
| S2 | `POST /score` avec une mauvaise clé | 401 | 401 | **OK** |
| S2b | `POST /score` avec une clé contenant un caractère non ASCII (ex. `clé`) | 401 | **500 Internal Server Error** ; le journal montre `TypeError: comparing strings with non-ASCII characters is not supported` (comparaison de clé). | **Bogue confirmé** (reproduit avec `X-API-Key: clé`, HTTP/2 500) : à corriger (comparer des octets, pas des chaînes) ; un client peut provoquer des erreurs 500 à volonté |
| S3 | Appel en HTTP (sans TLS) | redirection vers HTTPS | 301 vers `https://…:443/health` | **OK** |
| S4a | Texte vide | 422 | 422 | **OK** |
| S4b | Texte de 6 000 caractères (> 5 000) | 422 | 422 | **OK** |
| S4c | Corps qui n'est pas du JSON | 422 | 422 | **OK** |
| S5 | Les logs ne contiennent pas le texte reçu | aucun texte ni IP dans Cloud Logging | Texte envoyé : un nom, une IP et un mot unique (`ZEBRAXYZ123`). Recherche dans Cloud Logging (30 min) : **aucun résultat**. Les lignes du journal ont toutes la forme `score=60 longueur=67 duree_ms=80.2` (jamais le texte). | **OK** |
| S6 | `/docs` (Swagger) accessible sans clé | à décider | **200 : publique** | constat |
| S7 | Rafale de requêtes invalides (sans clé, mauvaise clé, texte trop long, JSON invalide) pendant que des utilisateurs légitimes travaillent | le service légitime continue | 2 min, 2 légitimes + 8 attaquants (`loadtest/attaque.py`). **5 812 requêtes d'attaque (≈ 49/s), toutes refusées avec le bon code** (401 ou 422), médiane 25 ms. **Utilisateurs légitimes : 276 requêtes, 0 erreur, médiane 90 ms, P95 170 ms, maximum 391 ms.** | **OK** (limite : pas de mesure « légitimes seuls » avec les mêmes textes, donc la comparaison n'est qu'indicative) |
| S8 | Limitation de débit | requêtes refusées (429) au-delà d'un seuil | Aucun 429 : les ≈ 49 requêtes/s d'un même client ont toutes été traitées jusqu'au refus (401/422). Une attaque plus forte consommerait du CPU sans être freinée. | constat : non implémentée (amélioration proposée : limite par clé ou par IP au niveau du load balancer) |

## Supervision (Prometheus et Grafana)

Charge de l'essai : montée progressive Locust lancée depuis un Mac, de 14:50 à 14:57 (heure de Paris, affichage Grafana). Captures dans [images/](images/).

| ID | Test | Attendu | Résultat | État |
|---|---|---|---|---|
| SU1 | Prometheus collecte les 2 pods de l'API (port 9090, séparé du port public) | 2 cibles `UP` | 2/2 `UP`, collecte en 6 à 14 ms ([capture](images/prometheus_cibles_up.png)) | **OK** |
| SU2 | Nombre de pods et autoscaler visibles | 2 pods, puis plus sous charge | 2 → 3 (≈ 14:55) → 5 (≈ 14:56:30) → 2 (≈ 15:01:30) ([capture](images/prometheus_pods_prets.png)) | **OK** |
| SU3 | CPU par pod | saturation visible sous charge | 1,0 cœur (le maximum alloué) sur les 2 pods d'origine de 14:52 à 14:57 ; les pods ajoutés servent trop tard ([capture](images/prometheus_cpu_par_pod.png)) | **OK** |
| SU4 | Mémoire par pod | marge suffisante | 0,5 à 0,65 Go au repos, 1,43 Go au pic (limite 2 Gi), non rendue après la charge ([capture](images/prometheus_memoire_par_pod.png)) | **OK** |
| SU5 | Débit de l'API | courbe proportionnelle à la charge | pic ≈ 12,5 requêtes/s, 0 après la fin ([capture](images/prometheus_requetes_par_s.png)) | **OK** |
| SU6 | Taux d'erreurs 5xx | visible s'il y en a | aucune série : **aucune erreur 5xx** renvoyée par les pods | **OK** |
| SU7 | Latence P95 | monte avec la charge, alerte à 2 s | **courbe bloquée à 1 s** : les intervalles de mesure par défaut s'arrêtent à 1 s, alors que Locust mesurait 8 à 12 s à 50-100 utilisateurs ([capture](images/prometheus_latence_p95.png)). **Non exploitable au-dessus de 1 s.** | limite : à corriger (intervalles à élargir côté API) |
| SU8 | Tableau de bord Grafana (Kubernetes / Compute Resources / Namespace) | CPU et mémoire par pod | « CPU Requests » affiché ; panneaux d'usage vides : GKE Autopilot ne laisse pas Prometheus lire les métriques kubelet/cAdvisor ([capture](images/grafana_dashboard_pods.png)). Remplacé par les métriques du processus exposées par l'API (SU3, SU4). | contourné |
| SU9 | Tableau de bord Grafana construit pour l'API ([grafana_dashboard.json](grafana_dashboard.json), importable) | indicateurs et courbes alimentés par Prometheus pendant une charge de 5 utilisateurs | 9 panneaux affichés : 2 pods prêts, ≈ 4,7 req/s, 0 erreur 5xx, CPU total ≈ 1,02 cœur (≈ 0,5 par pod), mémoire de 640 à 770 MiB par pod ([capture](images/grafana_tableau_de_bord.png), [bas de page](images/grafana_tableau_de_bord_bas.png)). L'autoscaler ne monte pas : 0,5 cœur par pod reste sous son seuil (70 % de 1 cœur). | **OK** |

## Stress

| ID | Test | Attendu | Résultat | État |
|---|---|---|---|---|
| ST1 | Montée 1 → 10 → 50 → 100 utilisateurs | l'API répond, la latence monte | 4 erreurs sur 3 616 (≈ 0,1 %) ; P95 de 1,2 s à 11,8 s ; débit jusqu'à 17-20 requêtes/s (5 pods) | **OK** |
| ST2 | +10 utilisateurs/20 s jusqu'à P95 > 2 s | point de rupture | 20 utilisateurs (≈ 8 requêtes/s, 2 pods), 0 erreur | **OK** |
| ST3 | Autoscaler | ajoute des pods quand le CPU dépasse 70 % | 5 pods atteints ; un pod neuf prêt en 5 min 29 s | **OK**, jugé trop lent |
| ST4 | Point de rupture « dur » (erreurs) | première vague d'erreurs | non atteint jusqu'à 100 utilisateurs | à faire si besoin (monter plus haut, coût) |

## Failover

| ID | Test | Attendu | Résultat | État |
|---|---|---|---|---|
| F1 | Suppression propre d'un pod (`kubectl delete`) sous charge de 5 utilisateurs | pas d'erreur, latence stable | 0 erreur sur 1 192 requêtes ; P95 628 ms avant, ≈ 465 ms après ; 5 pods avant l'incident | **OK** (limites : arrêt propre, 59 s observées) |
| F2 | Arrêt brutal d'un pod (`--grace-period=0 --force`) sous charge de 5 utilisateurs | quelques erreurs possibles, retour rapide | Pod supprimé à 14:41:25 UTC (t = 34 s). **1 erreur sur 771 requêtes** (502 Bad Gateway du load balancer, 2 s après le kill). Médiane 207 → 199 ms, P95 715 → 572 ms. Débit descendu à ≈ 4,3 req/s pendant ≈ 10 s, puis revenu à ≈ 5. 5 pods prêts avant l'incident. ([courbes](../loadtest/images/f2_courbes.png), [kubectl](../loadtest/images/f2_kubectl.png), [Locust](../loadtest/images/f2_locust_ui.png)) | **OK** (limite : 5 pods, pas le pire cas) |
| F3 | Perte d'un pod quand il n'en reste que 2 (charge de 5 utilisateurs) | service maintenu, capacité divisée par 2 | Pod supprimé de force à 14:51:09 UTC (t = 78 s) : **0 erreur sur 892 requêtes**. **Le pod de remplacement a mis 7 min 27 s à être prêt** (créé à 14:51:10, prêt vers 14:58:37) : il est resté `Pending`, l'autoscaler de machines a échoué (`FailedScaleUp : GCE quota exceeded`, puis « in backoff »). Un seul pod prêt pendant tout ce temps. Latence : médiane 240 → 394 ms, **P95 779 → 1 092 ms**, maximum 4,7 s ; débit ≈ 4,7 → ≈ 4 req/s. ([courbes](../loadtest/images/f3_courbes.png)) | **OK** : service maintenu mais dégradé ; **constat : la reprise dépend de la capacité que Google accepte de fournir (message `GCE quota exceeded`), pas seulement de Kubernetes. Quotas relevés ensuite (hors charge) : régionaux non pleins (CPUS 8/32, INSTANCES 1/8, adresses IP 1/4) ; **le plus serré est la limite globale du projet, `CPUS_ALL_REGIONS` = 12** (4/12 hors charge). Hypothèse la plus plausible : cette limite de 12 CPU a été atteinte quand l'API, Prometheus et Grafana occupaient le plus de machines ; non vérifiable après coup** |
| F3b | Protection contre les évictions volontaires (PodDisruptionBudget) | une règle empêche de retirer le dernier pod prêt | `kubectl get pdb` : **aucune règle**. Pendant F3, le pod survivant a été arrêté (`Terminating`) alors que son remplaçant n'était pas encore prêt : fenêtre probable d'environ 20 s sans pod prêt (déduite des âges des pods, non mesurée). | constat : amélioration proposée (PDB `minAvailable: 1`), non appliquée |
| F4 | Perte de tous les pods d'un nœud | — | — | à voir avec Enzo |

Détails, courbes et captures : [loadtest/RAPPORT.md](../loadtest/RAPPORT.md).
