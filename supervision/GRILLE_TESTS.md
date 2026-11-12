# Grille de tests : sécurité, stress, failover

Livrable du TP (« Grille tests sécurité/stress/failover »). Cible : l'API déployée sur GKE. Date des essais : 12 novembre 2026.

Légende : **OK** = vérifié sur le cluster ; **code** = prévu dans le code (tests `pytest` de la branche Enzo), pas vérifié sur le cluster ; **à faire**.

## Sécurité

| ID | Test | Attendu | Résultat | État |
|---|---|---|---|---|
| S1 | `POST /score` sans clé | 401 | 401 | **OK** |
| S2 | `POST /score` avec une mauvaise clé | 401 | 401 | **OK** |
| S3 | Appel en HTTP (sans TLS) | redirection vers HTTPS | 301 vers `https://…:443/health` | **OK** |
| S4a | Texte vide | 422 | 422 | **OK** |
| S4b | Texte de 6 000 caractères (> 5 000) | 422 | 422 | **OK** |
| S4c | Corps qui n'est pas du JSON | 422 | 422 | **OK** |
| S5 | Les logs ne contiennent pas le texte reçu | aucun texte ni IP dans Cloud Logging | test dans le code ; **à vérifier dans Cloud Logging** (envoyer un texte avec un nom et une IP, puis chercher) | code |
| S6 | `/docs` (Swagger) accessible sans clé | à décider | **200 : publique** | constat |
| S7 | Rafale de requêtes sans clé : le service légitime continue-t-il ? | P95 des requêtes légitimes inchangé | — | à faire (`loadtest/attaque.py`) |
| S8 | Pas de limitation de débit | requêtes refusées (429) au-delà d'un seuil | non implémentée | constat |

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
| F2 | Arrêt brutal d'un pod (`--grace-period=0 --force`) | quelques erreurs possibles, retour rapide | — | à faire |
| F3 | Perte d'un pod quand il n'en reste que 2 | service maintenu, capacité divisée par 2 | — | à faire (attendre le retour à 2 pods) |
| F4 | Perte de tous les pods d'un nœud | — | — | à voir avec Enzo |

Détails, courbes et captures : [loadtest/RAPPORT.md](../loadtest/RAPPORT.md).
