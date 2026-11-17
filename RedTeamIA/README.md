# RedTeamIA : simulation interne de l'attaque du professeur

Le 16 novembre, le professeur a attaqué les API de 9 équipes avec un outil « Red Team IA » multi-agents. Ses résultats sont dans `cours/RAPPORT-CONSOLIDE.md` (fichier non publié : il cite les autres équipes) : chez nous, **43 685 requêtes acceptées en 4 minutes et un P95 multiplié par 76**.

Ce dossier rejoue la même campagne **contre notre propre API**, défenses en service, pour vérifier ce qu'elles valent avant qu'il relance son outil. Il est **isolé** du projet : rien dans `api/`, `attack/` ou la pipeline n'en dépend, et il ne réutilise aucun code du projet.

Les résultats (deux exécutions) et leur analyse avant / après sont dans `LIVRABLES/TP2_LIVRABLE.md`, § 4.4 ; les fichiers bruts dans `attack/results/redteam/`.

## Correspondance avec l'outil du professeur

| Outil du professeur | Ici |
|---|---|
| Reconnaissance (modèle de langage) + `nmap`, `nuclei` | `v1_reconnaissance` : routes, fichiers sensibles, routes d'autres équipes, ports |
| Sondes `web.*` | `v2_sondes_web` : en-têtes, HTTPS, CORS, méthodes, pare-feu applicatif |
| Contrôle d'accès | `v3_authentification` : clés mal formées, force brute, effet sur un client légitime |
| Exposition du score, du seuil, du modèle | `v4_fuite_information` : réponse minimale, JSON malformé |
| Extraction de modèle | `v5_extraction` : 400 requêtes rapides, comme sa sonde |
| 7 sondes `llm.*` | `v6_evasion_sondes_ia` : déguisements, noyage, injection d'instruction, langue, Unicode |
| `impact.load` (128 requêtes simultanées) | `v7_deni_service` : 180 req/s, 128 simultanées, 120 s, avec la clé |
| — (il tirait d'une seule adresse) | `v8_multi_adresses` : deux adresses à la fois (poste et pod du cluster) |
| `impact.crash` / `impact.destroy` | **Non rejoués** : risque de casser la production pour peu d'information |

Il y a une différence : sa reconnaissance utilisait un modèle de langage, la nôtre est déterministe. Les sondes sont équivalentes, mais une liste fixe ne peut pas improviser.

## Cadre et garde-fous

- **La cible est uniquement notre API.** L'adresse et la clé sont lues dans l'environnement et ne sont jamais écrites. Les résultats remplacent l'adresse par `<cible>`.
- **Plafonds** : 180 requêtes/s, 128 requêtes simultanées, 120 s par tir, 100 000 requêtes au maximum.
- **Arrêt automatique (kill switch)** dans l'un de ces cas :
  - plus de 20 % d'erreurs serveur sur 10 s ;
  - un P95 de plus de 10 s ;
  - un pod de l'API qui redémarre.
- **Bouton d'arrêt d'urgence** dans l'interface. Le nettoyage supprime toujours les pods temporaires.
- **Un utilisateur légitime mesuré en continu** : un pod du cluster appelle `/score` toutes les 2 s par l'adresse publique, depuis une autre adresse que l'attaquant. C'est ce que le rapport du professeur ne mesurait pas.
- **Coût** : l'autoscaler monte jusqu'à 5 pods pendant quelques minutes. Il faut prévenir l'équipe avant les vagues 7 et 8.

## Lancer

Depuis la racine du dépôt, avec l'environnement `.venv` du projet et un accès `kubectl` au cluster :

```bash
export URL=https://<adresse de notre API>
export API_KEY="$(kubectl get secret dss-api-key -o jsonpath='{.data.API_KEY}' | base64 -d)"

# Interface : tableau de bord en direct, http://127.0.0.1:8060
.venv/bin/python RedTeamIA/interface/serveur.py

# Ou en ligne de commande
.venv/bin/python RedTeamIA/orchestrer.py              # vagues 1 à 6, sans impact
.venv/bin/python RedTeamIA/orchestrer.py --impact     # + vagues 7 et 8 (déni de service)
.venv/bin/python RedTeamIA/orchestrer.py --vague v3   # une seule vague
```

**L'ordre compte.** Les vagues qui ont besoin d'une adresse non bloquée (évasion) passent avant celles qui la font bloquer (force brute, extraction, déni de service).

## Interface

`interface/serveur.py` lance les vagues et diffuse chaque mesure au tableau de bord, `interface/dashboard.html`. Il affiche en direct :
- **les indicateurs** : requêtes d'attaque, acceptées, 429, 503, erreurs, succès et P95 de l'utilisateur légitime, pods, alertes ;
- **les vagues** : l'état de chacune et son résultat ;
- **la charge** : les réponses à l'attaquant par seconde et par code ;
- **l'utilisateur légitime** : la latence de chacune de ses requêtes, colorée par phase (référence, attaque, récupération) ;
- **la supervision** : les pods prêts et voulus par l'autoscaler, et les alertes Prometheus (déclenchées ou en attente) ;
- **les sondes et attaques ciblées** : la liste des sondes, la grille de force brute, la courbe du vol de modèle, l'évasion par déguisement ;
- **la comparaison** avec le tir du professeur.

L'interface elle-même est protégée :
- elle n'écoute que sur `127.0.0.1` ;
- la clé ne quitte jamais le serveur ;
- les actions exigent un en-tête qu'une autre page web ne peut pas envoyer, ce qui la protège contre le CSRF.

## Contenu

```
orchestrer.py        enchaîne les vagues dans le bon ordre
commun.py            cible, clé, écriture des résultats (adresse masquée), Prometheus, Kubernetes, événements
attaquant.py         générateur de charge (bibliothèque standard : tourne aussi dans un pod)
vagues/              v1 à v8, et rapport.py (synthèse automatique et graphique)
interface/           serveur local et tableau de bord
resultats/           un JSON par vague, synthese.md, deni_service.png
(analyse : LIVRABLES/TP2_LIVRABLE.md, § 4.4)
```
