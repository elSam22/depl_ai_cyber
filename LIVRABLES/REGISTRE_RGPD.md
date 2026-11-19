<!-- Copie du registre en Annexe C de TP1_LIVRABLE.md (version 1.2) : modifier les deux ensemble. -->
# Registre des activités de traitement — article 30 RGPD

**Référence** : DSS-RGPD-2026-001
**Version** : 1.2 (relue contre le code en service, branche `ci`)
**Date** : 17 novembre 2026 (ajouts du 19 novembre : voir § 9)
**Statut** : En vigueur

> **État au 17 novembre, après les corrections du TP2.** Le corps de ce livrable décrit l'API telle qu'elle était le 13 novembre (version 1.1 du registre). Les écarts avec les § 4 à 7 (limitation de débit, `/docs` fermé, alertes, réponse réduite au score et au verdict) sont les corrections du TP2, résumées dans le TP2 § 5.9.

---

## 1. Responsable du traitement

| Champ | Valeur |
|---|---|
| Dénomination | Équipe Digital Social Score (CAKPOSSA Jean-Philippe, OUEDRAOGO Eliana, NOUDEGBE Situ) |
| Projet | Digital Social Score API — analyse de toxicité (TP ESIGELEC) |
| Contact | Les membres de l'équipe, joignables par l'ESIGELEC (adresses non publiées : dépôt public). Projet pédagogique : aucune adresse dédiée n'existe |
| Localisation | France |

---

## 2. Traitement A — Préparation du jeu d'entraînement (notebooks)

| Rubrique | Contenu |
|---|---|
| Finalité | Réduire la présence de données personnelles dans les commentaires avant l'entraînement des modèles (cadre pédagogique) |
| Base légale | Art. 6.1.f — intérêt légitime : commentaires publics publiés sous licence libre, utilisés pour un exercice de détection de toxicité ; données pseudonymisées avant tout usage |
| Source | Toxic Comment Classification Dataset (Jigsaw / Google, 2017) : 159 571 commentaires d'entraînement, 153 164 de test ; texte CC-BY-SA 3.0 (Wikipédia), labels CC0 ; annotation binaire par vote majoritaire d'évaluateurs humains ; **biais** : corpus uniquement anglophone, issu de Wikipédia, biais culturels possibles sur `identity_hate` |
| Données | Texte libre pouvant contenir noms, pseudos, adresses IP, e-mails, téléphones, URL, adresses postales. Les labels (notamment `identity_hate`) peuvent révéler des attaques visant des groupes : données potentiellement sensibles (art. 9) |
| Personnes concernées | Auteurs et personnes citées dans les commentaires Wikipédia |
| Minimisation | Identifiants directs remplacés par 8 balises typées (regex + spaCy NER) avant l'entraînement. **Pseudonymisation, pas anonymisation** : le texte d'origine reste public sur Wikipédia |
| Stockage | Fichiers anonymisés et nettoyés (`data/anonymise/`, `data/clean/`) : en local seulement, exclus de Git |
| **Jeu brut** | **`data/train.csv` et `data/test.csv` (≈ 130 Mo) sont publiés dans le dépôt GitHub public** `elSam22/depl_ai_cyber`. Texte déjà public et sous licence, mais republié sans pseudonymisation, sur un hébergement situé aux États-Unis. **Action : retirer ces fichiers de l'historique Git et documenter le téléchargement depuis Kaggle** |
| Conservation | Fichiers anonymisés et nettoyés : supprimés après la notation du projet |
| Destinataires | Équipe projet |
| Transferts hors UE | GitHub (États-Unis) : code, documentation, résultats agrégés **et jeu brut public** (voir ci-dessus) |
| Risques résiduels | Anonymisation incomplète (aucun jeu annoté pour la mesurer) ; ré-identification par recoupement avec Wikipédia |

---

## 3. Traitement B — API de score en service

| Rubrique | Contenu |
|---|---|
| Nom | Digital Social Score API — analyse automatisée de toxicité |
| Finalité principale | Restituer, pour un texte soumis, un score de toxicité de 0 à 100 (arrondi à la dizaine) et un verdict (`toxique`) |
| Finalité secondaire | Sécurité du service : détection et analyse d'abus (journaux du load balancer, refus pseudonymisés) |
| Base légale | Art. 6.1.f — intérêt légitime à fournir un outil d'aide à la modération ; mis en balance par la minimisation (texte jamais conservé, anonymisé avant le modèle) |
| Décision automatisée / profilage | Le score est calculé sans intervention humaine. Aucune décision à effet juridique dans la version actuelle. **Une AIPD (art. 35) serait obligatoire** si le score était intégré à un processus décisionnel (modération automatique, accès, recrutement) |

### 3.1 Personnes concernées

- **Utilisateurs de l'API** (développeurs, intégrateurs) : identifiés par une clé d'API **unique et partagée** ; la clé n'est jamais journalisée.
- **Auteurs des commentaires soumis**, et personnes citées dans ces commentaires.

### 3.2 Données traitées

| Donnée | Nature | Traitement | Stockage |
|---|---|---|---|
| Commentaire soumis | Données personnelles potentielles, y compris sensibles (art. 9 : opinions, santé, origine…) | Anonymisé (regex + spaCy NER) puis nettoyé, en mémoire, avant le modèle | **Aucun** — ni disque, ni journal, ni réponse |
| Réponse | Score arrondi à la dizaine + verdict | Renvoyée à l'appelant | Non conservée côté serveur |
| Journal de l'API | Score, longueur du texte, durée de calcul, horodatage : non personnel | Une ligne par analyse, par exemple `score=87 longueur=142 duree_ms=14.2` | Cloud Logging, 30 jours |
| Journal des refus (401, 429, 503, 413) | Motif, route, **empreinte HMAC de 10 caractères de l'adresse IP** (clé secrète du serveur) : donnée pseudonymisée | Au plus une ligne par minute et par client | Cloud Logging, 30 jours |
| **Journaux du load balancer** | **Adresse IP du client, chemin, code de réponse, user-agent, horodatage : données personnelles** | Activés volontairement (`sampleRate: 1.0`) pour pouvoir reconstituer une attaque | Cloud Logging, 30 jours |
| Métriques Prometheus | Compteurs par route, code, motif de refus ; CPU, mémoire : non personnel | Dans le cluster, port non exposé | Durée de rétention de Prometheus |

---

## 4. Destinataires et sous-traitants (art. 28)

**Destinataires internes** : les trois membres de l'équipe (journaux et supervision). Note : les trois membres ont le rôle `Owner` du projet Google Cloud (voir le rapport, § 5.3).

| Sous-traitant | Rôle | Localisation | Garanties |
|---|---|---|---|
| Google Cloud (GKE, Artifact Registry, Cloud Build, Cloud Logging, Cloud Storage) | Hébergement, construction de l'image, journaux, stockage des poids du modèle | europe-west9 (Paris) pour le cluster et le dépôt d'images | Avenant de traitement des données Google Cloud (CCT) |
| Google Secret Manager | Stockage de la clé d'API | **Réplication automatique (multi-régions choisies par Google)** : créé avec `--replication-policy=automatic` | ISO 27001, SOC 2 ; **action : restreindre la réplication à europe-west9** |
| GitHub (Microsoft) | Code source, pipeline | États-Unis | Pas de donnée de production ; jeu brut public (traitement A) |
| Google Fonts | Police du front de démonstration | Hors UE possible | Connexion directe du navigateur vers Google (adresse IP) ; **action : héberger la police localement** |

### Transferts hors UE (art. 30.1.e)

Le calcul du score et les journaux de production restent dans l'UE. Il existe trois flux hors UE ou non localisés : le dépôt GitHub (jeu brut public), la réplication du secret, et la police Google Fonts chargée par le front de démonstration.

---

## 5. Durées de conservation

| Données | Durée | Justification |
|---|---|---|
| Texte soumis | Aucune — mémoire uniquement | Minimisation (art. 5.1.c) |
| Journaux de l'API, des refus et du load balancer | **30 jours** — rétention par défaut de Cloud Logging, non modifiée | Sécurité et traçabilité, mises en balance avec la minimisation |
| Poids du modèle | Durée du service | Nécessité opérationnelle |
| Fichiers du traitement A | Jusqu'à la notation | Projet pédagogique |

---

## 6. Mesures de sécurité (art. 32)

| Mesure | Mise en œuvre | Statut |
|---|---|---|
| Authentification | Clé `X-API-Key`, comparaison à temps constant (`secrets.compare_digest`, `api/main.py`) ; 429 après 10 clés fausses par minute et par adresse | En service — défaut : une clé non ASCII donne 500 au lieu de 401 |
| Chiffrement en transit | HTTPS forcé (certificat géré, redirection : `api/k8s/ingress.yaml`, `backendconfig.yaml`) ; pas de TLS entre le load balancer et les pods | En service |
| Minimisation | Anonymisation avant le modèle (`api/preprocessing.py`) ; texte jamais journalisé (`api/main.py`, `--no-access-log` dans `api/Dockerfile`) (prouvé par un canari) ; réponse réduite | En service |
| Secrets | Secret Manager → Secret Kubernetes (`secretKeyRef` dans `api/k8s/deployment.yaml`) ; jamais dans le code, l'image ou Git ; poids du modèle dans un bucket privé | En service |
| Durcissement | Non-root, `drop ALL`, pas d'élévation (`api/Dockerfile`, `api/k8s/deployment.yaml`), système de fichiers en lecture seule, aucun rôle Google Cloud pour les pods | En service |
| Protection en entrée | Texte de 1 à 5 000 caractères (422, `api/main.py`) ; limites par adresse (429, `api/limiteur_debit.py`), corps ≤ 40 Ko (413), au plus 3 calculs par pod (503), `/docs` fermé | En service depuis le 16 novembre |
| Disponibilité | 2 à 5 pods, sondes de santé (`api/k8s/deployment.yaml`, `hpa.yaml`) | En service |
| Supervision | Prometheus, Grafana, 7 règles d'alerte (sans notification) | En service |
| Droits d'accès | 3 comptes `Owner` | **À réduire** |

---

## 7. Droits des personnes (art. 12 à 22)

Les journaux ne contiennent **aucun identifiant de clé** et aucun texte. Les droits s'exercent donc ainsi :

| Droit | Applicable | Modalités |
|---|---|---|
| Accès (art. 15) | Limité | Le texte n'est pas conservé. Pour les journaux du load balancer, une personne peut demander les lignes liées à **son adresse IP** sur les 30 derniers jours |
| Rectification (art. 16) | Sans objet | Aucune donnée conservée qui puisse être inexacte au sujet d'une personne |
| Effacement (art. 17) | Oui | Suppression des lignes liées à une adresse IP sur demande ; suppression automatique à 30 jours |
| Limitation (art. 18) | Limité | Pas de donnée à geler, en dehors des journaux du load balancer |
| Portabilité (art. 20) | Sans objet | Traitement fondé sur l'intérêt légitime, aucune donnée fournie et conservée |
| Opposition (art. 21) | Oui | Arrêt de l'envoi de textes ; la clé étant partagée, une révocation individuelle est impossible (clé par client à prévoir) |
| Décision automatisée (art. 22) | À garantir | Le score ne doit pas être la seule base d'une décision à effet juridique |

**Contact** : les membres de l'équipe, par l'ESIGELEC (en service réel, une adresse dédiée serait obligatoire). **Réclamation** (art. 77) : CNIL, 3 place de Fontenoy, TSA 80715, 75334 Paris Cedex 07, www.cnil.fr.

---

## 8. Risques résiduels

- Anonymisation non mesurée et incomplète ; ré-identification possible par recoupement avec Wikipédia.
- Données sensibles possibles dans les commentaires soumis (traitées en mémoire seulement).
- Jeu brut publié sur GitHub.
- Score non calibré : ne doit pas fonder seul une décision.
- Accès trop larges au projet (trois `Owner`) : chacun peut lire la clé et les journaux.

---

## 9. Historique des révisions

| Version | Date | Modifications |
|---|---|---|
| 1.0 | 12/11/2026 | Création initiale |
| 1.1 | 13/11/2026 | Relecture contre le code en service : deux traitements distingués ; journaux du load balancer (IP) ajoutés ; rétention unifiée à 30 jours ; réplication du secret, Google Fonts et jeu brut public déclarés ; droits reformulés selon ce qui est réellement possible |
| 1.2 | 17/11/2026 | Corrections du TP2 : journal des refus (empreinte HMAC), protection en entrée (limites, plafond de calculs, `/docs` fermé), réponse réduite, 7 alertes, poids du modèle en bucket privé. Ajouts du 19/11 : annotation et biais du jeu de données, ligne type du journal, fichiers sources des mesures de sécurité (repris du registre d'Eliana) |

*Établi en application de l'article 30 du règlement (UE) 2016/679 (RGPD).*
