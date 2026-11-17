# Digital Social Score

**API de détection de toxicité : de l'analyse de texte à une infrastructure cloud sécurisée, scalable et conforme**

**CAKPOSSA Jean-Philippe · OUEDRAOGO Eliana · NOUDEGBE Situ**

TP1 — Déploiement de solutions IA et cybersécurité — ESIGELEC — novembre 2026
Dépôt : github.com/elSam22/depl_ai_cyber (code en service : branche ci)

---

## Résumé

Nous avons conçu, entraîné, déployé et sécurisé une API qui reçoit un commentaire et renvoie un **score de toxicité de 0 à 100**. Le texte est **anonymisé avant le modèle** (regex + spaCy NER) et n'est **jamais stocké ni journalisé**.

- **Modèle** : trois modèles comparés sur le même jeu de test (BiLSTM, DistilBERT, LAYA en zéro-shot). **DistilBERT** est déployé : meilleure AUC-PR (0,590) et meilleur F1 (0,558), inférence de 8 ms.
- **Infrastructure** : GKE Autopilot à Paris (europe-west9), HTTPS géré par Google, clé d'API dans Secret Manager, conteneur non-root, 2 à 5 pods avec autoscaler.
- **Mesures** : environ 4 requêtes/s par pod ; rupture de latence (P95 > 2 s) à 20 utilisateurs ; perte d'un pod sur 2 sans erreur.
- **Incident réel** : le 16 novembre, l'API a reçu 94 000 requêtes hostiles. Nous l'avons détectée, analysée et corrigée le jour même ; 7 règles d'alerte en sont issues.
- **Ce qui reste faible**, dit sans détour : deux comptes `Owner` superflus (Enzo et Situ, à corriger en fin de TP), une seule clé d'API partagée, un bogue de la clé non ASCII (erreur 500), une anonymisation non garantie.

---

## Sommaire

1. Introduction
2. Données et anonymisation (étape 1)
3. Modèles (étape 2)
4. Déploiement et API (étape 3)
5. Sécurité et conformité RGPD (étape 4)
6. Montée en charge (étape 5)
7. Supervision, alertes et incidents (étape 6)
8. Architecture cloud (étape 7)
9. Originalité et curiosité technique
10. Limites, risques résiduels et améliorations priorisées
11. Conclusion

- Annexe A — Reproduire
- Annexe B — Grille de tests complète et rapport de charge

---

## 1. Introduction

**Objectif.** Le sujet demande une API qui détecte la toxicité d'un texte (injure, racisme, harcèlement, propos haineux), lui attribue un score de 0 à 100, respecte le RGPD, tient la charge, est observable et documentée par un schéma d'architecture justifié.

**Démarche.** Nous avons suivi les 7 étapes du sujet dans l'ordre, en mesurant chaque choix. Chaque section donne le choix retenu, l'alternative écartée, la raison et ce que nos mesures en ont montré.

**Chaîne de traitement.** anonymisation → nettoyage → modèle → 6 probabilités → seuils par label → score 0-100.

### Nos principes de choix

Tous nos choix découlent de cinq principes. Les tableaux de justification des sections suivantes y renvoient (P1 à P5) au lieu de répéter le raisonnement.

| Principe                                                         | Ce qu'il veut dire concrètement                                                                                                                                                                          |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **P1 — Un outil spécialisé par tâche**                 | Pour chaque problème, l'outil le plus simple qui le résout bien. Une regex pour un format fixe, un modèle statistique pour ce qui demande du contexte. Pas d'outil universel qui fait tout moyennement |
| **P2 — Mesurer, puis vérifier en charge**                | Un choix est fait sur une mesure (temps, qualité, mémoire), puis confirmé ou corrigé par les tests de l'étape 5.                                                                                     |
| **P3 — Minimiser les données (RGPD dès la conception)** | Ce qui n'est pas collecté ou pas stocké ne peut pas fuiter. Le texte est anonymisé avant le modèle et n'est jamais écrit                                                                             |
| **P4 — Refuser tôt et à bas coût**                     | Les contrôles les moins chers (taille, débit, clé, format) passent avant les traitements coûteux (NER, modèle) : un attaquant doit coûter plus cher à l'API qu'il ne lui coûte                    |
| **P5 — Tenir dans un budget étudiant**                   | Un Mac M3 16 Go pour l'entraînement, des crédits Google Cloud limités et un quota de 12 CPU pour le projet. Chaque ressource demandée est facturée                                                   |

Chaque tableau de justification suit le même fil : **besoin** (fonctionnel), **choix**, **raison technique**, **alternative écartée**, et quand elle existe, **la mesure qui a validé le choix**.

| Étape                          | Fichiers                                                |
| ------------------------------- | ------------------------------------------------------- |
| 1. Anonymisation                | `notebooks/anonyme_2.ipynb`, `api/preprocessing.py` |
| 2. Nettoyage                    | `notebooks/clean_text.ipynb`                          |
| 3. Entraînement et comparaison | `notebooks/train.ipynb`                               |
| 4. API et déploiement          | `api/main.py`, `api/k8s/`, `api/deploy/`          |
| 5. Tests de charge              | `loadtest/`                                           |
| 6. Supervision                  | `supervision/`                                        |

---

## 2. Données et anonymisation (étape 1)

### 2.1 Jeu de données

**Toxic Comment Classification Dataset** (Jigsaw / Google, 2017) : commentaires des pages de discussion de Wikipédia en anglais.

| Caractéristique     | Détail                                                                         |
| -------------------- | ------------------------------------------------------------------------------- |
| Volume               | 159 571 commentaires d'entraînement ; 153 164 de test, dont 63 978 labellisés |
| Labels (multi-label) | toxic, severe_toxic, obscene, threat, insult, identity_hate                     |
| Licences             | Texte : CC-BY-SA 3.0 (Wikipédia) ; labels : CC0                                |
| Déséquilibre       | ≈ 10 % de positifs sur `toxic` ; `threat` et `identity_hate` < 1 %       |
| Biais                | Corpus uniquement anglophone ; biais culturels possibles sur identity_hate      |

**Pourquoi ce jeu plutôt que GameTox.** Une tâche multi-label réaliste, un volume suffisant pour comparer trois architectures, des labels issus d'un vote majoritaire d'annotateurs humains.

### 2.2 Méthode : regex puis NER, en un seul passage

**Le besoin.** Fonctionnellement, le sujet impose qu'aucune donnée personnelle ne soit conservée en clair et que l'on utilise un NER. Techniquement, les données personnelles d'un commentaire sont de deux natures très différentes. Certaines ont une **forme fixe** (une adresse e-mail a toujours un @ et un domaine, une IPv4 a quatre nombres séparés par des points). D'autres n'en ont **aucune** : « Paris » peut être une personne, une ville ou un nom d'hôtel, et seul le contexte de la phrase le dit.

**Pourquoi deux outils plutôt qu'un (P1).**

- **La regex** est exacte et explicable sur les formats fixes : elle trouve chaque e-mail bien formé, en quelques microsecondes, et l'on sait toujours pourquoi elle a masqué un mot. En revanche, elle est incapable de reconnaître un nom propre.
- **Le NER de spaCy** lit le contexte et reconnaît « John Smith » comme une personne. Mais `en_core_web_sm` n'**a pas d'étiquette pour les e-mails, les IP ou les téléphones** : seul, il laisserait passer précisément les identifiants les plus directs.
- **Ensemble**, chacun couvre l'angle mort de l'autre. La regex est prioritaire en cas de chevauchement, parce qu'elle est déterministe : on préfère sa réponse sûre à une probabilité du NER.

**Pourquoi un traitement local (P3).** spaCy tourne dans le conteneur. Un service d'anonymisation en ligne (API de détection de personnes d'un fournisseur cloud, ou un LLM) obligerait à **envoyer le texte brut à un tiers pour le protéger**, ce qui contredit la finalité de l'étape. Un LLM coûterait en plus des centaines de millisecondes par commentaire, contre 3 ms ici.

**Comment ça marche.**

- **Regex** pour ce qui a un format fixe : e-mail, téléphone, URL, adresse IP, pseudo (`@x`, `User:x`), adresse postale précise.
- **spaCy** `en_core_web_sm` pour ce qui n'a pas de format : noms de personnes (`PERSON`) et d'organisations (`ORG`).
- La regex est **prioritaire** : on fusionne les deux listes de positions, puis on remplace en **un seul passage** sur le texte d'origine. Remplacer en plusieurs passes décalerait les positions trouvées ensuite.
- Chaque élément devient une **balise typée** : `personne_tag`, `organisation_tag`, `email_tag`, `url_tag`, `ip_tag`, `telephone_tag`, `pseudo_tag`, `adresse_tag`.

| Besoin                                                                                      | Choix                                                                                         | Raison technique                                                                                                                                                 | Alternative écartée                                                                                         | Limite assumée                                       |
| ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| Traiter 310 000 lignes en un temps raisonnable, puis chaque requête de l'API en production | `en_core_web_sm` (P2, P5)                                                                   | Mesuré à ≈ 3 ms par commentaire pour tout le jeu ; 20 min pour le jeu complet, négligeable devant les 8 ms du modèle en service                             | `trf` (transformer) : plus précis, mais ≈ 100 fois plus lent sur CPU, et il doublerait la mémoire du pod | Moins précis sur les noms rares                      |
| Masquer ce qui identifie une personne, sans détruire le sens                               | PERSON et ORG seulement                                                                       | Un nom identifie une personne, une organisation peut identifier son employeur                                                                                    | Masquer aussi les lieux (GPE, LOC)                                                                            | ORG produit des faux positifs (jargon Wikipédia)     |
| Garder le signal de identity_hate                                                           | Villes et pays conservés (P1 appliqué à la finalité)                                      | Seuls, ils n'identifient pas personne ; or « les gens de [pays] » est exactement ce que le modèle doit apprendre. Les masquer crée en plus des faux positifs | Tout masquer                                                                                                  | Ré-identification possible par recoupement           |
| Ne pas effacer ce que le modèle doit apprendre                                             | Mots toxiques retirés des entités NER avant masquage                                        | Une insulte prise pour un nom (« moron ») et masquée rendrait le commentaire neutre pour le modèle                                                           | Faire confiance au NER                                                                                        | Une insulte déformée peut encore passer pour un nom |
| Que le modèle comprenne la phrase après masquage                                          | Balise typée (`personne_tag`)                                                              | La phrase garde sa structure, et « insulte + personne_tag » reste distinct de « insulte + organisation_tag »                                                 | Supprimer l'entité, ou une balise unique `[MASK]`                                                          | Révèle qu'une entité existait                      |
| Exactitude des positions                                                                    | Un seul passage, regex prioritaire                                                            | Remplacer en plusieurs passes décale les positions trouvées ensuite                                                                                            | Enchaîner `re.sub` puis NER                                                                                | —                                                    |
| Même traitement à l'entraînement et en production                                        | Code partagé (`api/preprocessing.py`, version du prétraitement exposée par `/version`) | Un modèle qui voit en production des textes formatés autrement qu'à l'entraînement se trompe sans prévenir                                                  | Réécrire le prétraitement dans l'API                                                                       | Le notebook et l'API doivent rester synchronisés     |

### 2.3 Avant / après : exemples exécutés

| Texte d'origine                                                                                         | Après anonymisation                                                                      | Lecture                                                         |
| ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Hi John Smith, please stop reverting my edits or I will report you to Microsoft.                        | Hi personne_tag, please stop reverting my edits or I will report you to organisation_tag. | NER : personne et organisation                                  |
| Contact me at jane.doe@example.com or call +33 6 12 34 56 78.                                           | Contact me at email_tag or call telephone_tag.                                            | Regex : e-mail et téléphone                                   |
| User:WikiFan42 your edit from 192.168.45.67 was vandalism, see https://fr.wikipedia.org/wiki/Talk:Paris | User:pseudo_tag your edit from ip_tag was vandalism, see url_tag                          | Regex : pseudo, IP, URL (l'URL entière, y compris « Paris ») |
| @darkknight you are a moron, I live at 221 Baker Street, London.                                        | @pseudo_tag you are a moron, I live at adresse_tag, London.                               | « moron » conservé ; adresse masquée, ville conservée      |
| I hate people from France, they are all idiots.                                                         | (inchangé)                                                                               | Choix voulu : le pays visé est le signal de identity_hate      |
| 13 rue pierre 75000 Paris                                                                               | (inchangé)                                                                               | **Échec connu** : nom de rue en minuscules               |
| Y0u 4re a st0pid 1diot                                                                                  | personne_tag a st0pid 1diot                                                               | **Faux positif** : le leetspeak est pris pour un nom      |

Après nettoyage, la dernière ligne devient `personne_tag a stopid 1diot` : la balise survit au nettoyage (le `_` est conservé), mais une partie de l'insulte est perdue. C'est une limite réelle de l'ordre des traitements, découverte en rédigeant ce rapport.

### 2.4 Corrections après lecture des sorties

La première version masquait trop. Nous avons lu les sorties et compté :

- insultes prises pour des noms (`moron` ×202), jargon Wikipédia (`Wikipedia` ≈ 19 % des ORG, `UTC`, `POV`), personnalités publiques, mots courants (`hi` ×189) ;
- un motif IPv4 incorrect laissait passer ≈ 1 100 adresses IP ;
- de fausses adresses détectées (années, `Way`, `Place`).

Corrections : listes de filtrage, règle « un mot isolé en minuscules n'est pas un nom », motif IPv4 corrigé, faux positifs d'adresse retirés.

**Résultat sur 20 000 lignes : 1,45 balise par commentaire au lieu de 1,93, et plus aucune insulte masquée par le NER.**

### 2.5 Ce que l'anonymisation ne garantit pas

- **Aucun jeu annoté à la main** : nous n'avons ni précision ni rappel chiffrés pour l'anonymisation.
- Les listes de filtrage sont faites à la main, donc incomplètes.
- Cas non couverts constatés : rue en minuscules, numéro à 9 chiffres, pseudo sans préfixe, leetspeak pris pour un nom.

**Conclusion : c'est de la pseudonymisation et de la minimisation, pas une anonymisation au sens du RGPD.** Le texte d'origine reste public sur Wikipédia : un auteur peut être ré-identifié par recoupement.

### 2.6 Nettoyage

Minuscules → suppression des emojis → suppression de la ponctuation (`[^\w\s]`) → espaces réduits à un seul.

Le `\w` conserve le `_` : les balises `xxx_tag` survivent. Le notebook vérifie que chaque balise apparaît le même nombre de fois avant et après. Limite acceptée : les majuscules et les `!!!` sont des indices de colère que l'on perd.

---

## 3. Modèles (étape 2)

### 3.1 Un protocole commun, pour une meilleure comparaison

| Jeu           | Contenu                                                                                                        | Rôle                                            |
| ------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| Entraînement | 30 000 lignes des 80 % de `train_clean.csv`, stratifiées sur la combinaison exacte des 6 labels (graine 42) | BiLSTM et DistilBERT (LAYA n'est pas entraîné) |
| Validation    | Les 20 % restants (31 915 lignes) ; 3 000 pour LAYA, trop lent                                                 | Choisir les seuils                               |
| Test          | 10 000 lignes du test Kaggle, graine 42, regardées **une seule fois** à la fin                         | Comparaison finale                               |

- **30 000 lignes** : temps d'entraînement acceptable sur un Mac M3 16 Go (DistilBERT : 64 min).
- **Stratification** : les classes rares (threat) restent présentes dans l'échantillon.
- **Lignes à -1 retirées du test avant toute prédiction** : elles ne sont pas évaluées par Kaggle (89 186 sur 153 164).
- **Test séparé de la validation** : les seuils sont réglés sur la validation, donc le résultat du test n'est pas optimiste.

### 3.2 Choix de modélisation

**Le besoin.** Fonctionnellement : un commentaire peut cumuler plusieurs formes de toxicité, et les plus graves (menace, haine identitaire) sont les plus rares, à moins de 1 %. Un modèle qui les ignore serait inutile pour la modération, même avec une excellente exactitude globale.

Techniquement : le modèle est appelé en ligne, sur CPU. Pour garder un P95 inférieur à 2 s avec plusieurs requêtes en file, une inférence doit coûter de l'ordre de la dizaine de millisecondes, pas de la seconde.

| Choix                                                                                                  | Justification                                                                                                                                                                       |
| ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 6 sorties sigmoïde (multi-label)                                                                      | Un commentaire peut être à la fois toxic, obscene et insult                                                                                                                       |
| `BCEWithLogitsLoss` avec `pos_weight` = négatifs / positifs                                       | Sans lui, les classes rares sont ignorées. Contrepartie : les probabilités sont gonflées                                                                                         |
| Seuil par label, réglé sur la validation (maximise le F1)                                            | Au seuil 0,5, le rappel est très haut et la précision très basse ; le seuil corrige l'effet du `pos_weight`. Limite : `threat` a peu de positifs, son seuil est moins stable |
| **BiLSTM** (embedding 128, 64 par sens, max-pooling, dropout 0,3, 3 époques, Adam 1e-3)         | Référence légère, sans pré-entraînement. Hyperparamètres choisis, non optimisés                                                                                             |
| **DistilBERT** (`distilbert-base-uncased`, 66 M de paramètres, 2 époques, lr 2e-5, batch 16) | Version distillée de BERT : bon compromis entre qualité et temps de calcul, à l'entraînement comme en service                                                                   |
| **LAYA en zéro-shot** (`convaiinnovations/laya`)                                              | Voir ci-dessous                                                                                                                                                                     |

**LAYA, le « modèle de décision » du sujet.** LAYA (Convai Innovations, licence Apache 2.0) repose sur un encodeur ModernBERT-large de 421 M de paramètres, six fois plus gros que DistilBERT. Il ne génère pas de texte : on lui pose **une question oui/non par label**, et la probabilité de « oui » sert de score. Nous ne l'avons **pas entraîné**, par décision de groupe, car les deux voies possibles étaient irréalistes sur notre machine :

- le fine-tuning complet demande 4 à 5 h sur 2 GPU T4, avec un script prévu pour un autre format de données ;
- `agent.fit` a été **mesuré à 7,6 s par ligne**, soit ≈ 63 h pour 30 000 lignes.

LAYA est donc un **plancher** : un modèle évalué sur le même test sans avoir vu une seule donnée d'entraînement.

### 3.3 Résultats (macro-moyenne sur les 6 labels, test commun de 10 000 lignes)

| Modèle              | ROC-AUC test    | AUC-PR test     | F1 (seuil 0,5) | Précision / rappel (seuil optimisé) | F1 (seuil optimisé) | Entraînement | Inférence |
| -------------------- | --------------- | --------------- | -------------- | ------------------------------------- | -------------------- | ------------- | ---------- |
| BiLSTM               | 0,916           | 0,362           | 0,231          | 0,301 / 0,481                         | 0,358                | 157 s         | 0,13 ms    |
| **DistilBERT** | **0,977** | **0,590** | 0,308          | 0,493 / 0,693                         | **0,558**      | 64 min        | 8,1 ms     |
| LAYA (zéro-shot)    | 0,969           | —              | 0,328          | 0,366 / 0,740                         | 0,476                | 0             | 700 ms     |

ROC-AUC sur la validation : 0,948 / 0,985 / 0,965. Détail par label : `models/resultats_par_label.csv`.

### 3.4 Pourquoi DistilBERT est déployé

- **Meilleure qualité** sur le test commun : AUC-PR 0,590 et F1 0,558.
- **8 ms d'inférence** : compatible avec une API en ligne. LAYA est ≈ 90 fois plus lent (700 ms).
- **L'AUC-PR est notre indicateur principal.** Avec ≈ 10 % de positifs, la ROC-AUC est gonflée par les vrais négatifs : BiLSTM a 0,916 de ROC-AUC mais seulement 0,362 d'AUC-PR.
- **Pourquoi pas BERT base ou RoBERTa.** Ils sont environ deux fois plus lourds que DistilBERT. Sur notre CPU, cela divise par deux la capacité par pod, déjà le goulot (§ 6.4), pour un gain de qualité que nous n'avons pas pu mesurer dans notre budget d'entraînement (P5).
- **Ce que la comparaison montre.** DistilBERT et LAYA reposent tous deux sur un encodeur de type BERT. Le petit modèle spécialisé par fine-tuning (66 M) bat le gros modèle généraliste (421 M), à la fois en qualité et en vitesse.

### 3.5 Le score de 0 à 100

- Score d'un label = probabilité × 100.
- Un label est « détecté » si sa probabilité atteint son seuil.
- **Score global = moyenne des scores des labels détectés** ; si aucun n'est détecté, score de `toxic`.

**Pourquoi ne pas faire la moyenne des 6 labels.** Un commentaire très toxique (`toxic` à 0,95) avec cinq autres labels à 0,02 obtiendrait ≈ 19 au lieu de 95 : le bruit des labels non déclenchés effacerait le signal.

**Limites.** Ce n'est pas une probabilité calibrée (le `pos_weight` la gonfle) ; 50 n'est pas la frontière du « toxique » ; un label faiblement détecté peut faire baisser la moyenne.

**En service** : Le score renvoyé est **arrondi à la dizaine** et accompagné du seul verdict `toxique`. Les probabilités et les seuils restent internes, parce qu'ils aideraient un attaquant à cloner le modèle ou à régler une évasion.

---

## 4. Déploiement et API (étape 3)

### 4.1 Chaîne de livraison

**Poids du modèle dans un bucket GCS privé** → **Cloud Build** construit l'image → **Artifact Registry** → **GKE Autopilot** (europe-west9, Paris).

- **Les poids ne sont jamais dans Git**, qui est public. Le bucket est privé (accès public interdit) ; la chaîne de livraison n'a que le droit de lecture.
- **Le modèle est intégré dans l'image** et Hugging Face tourne en mode hors ligne : aucun téléchargement au démarrage d'un pod, aucun appel externe en production.
- **Leçon du 13 novembre.** Un déploiement lancé depuis un clone Git a produit une image **sans modèle**. L'API est retombée **silencieusement** sur un modèle factice (`dummy-0`) tout en répondant 200. Depuis, on contrôle la version du modèle après chaque déploiement, et le dépôt est reproductible grâce au bucket.

### 4.2 Choix techniques du déploiement

| Besoin                                                                                                     | Choix                                                           | Raison technique                                                                                                                                                                               | Alternative écartée                                                                                                                                                                   | Validé par                                                                                           |
| ---------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Une API qui encaisse la charge, survit à la perte d'une instance et se teste en failover (étapes 5 et 6) | **Kubernetes (GKE)**                                      | Réplicas, sondes de santé, autoscaler et load balancer sont fournis et réglables ; on peut tuer un pod pour tester la reprise                                                               | Vertex AI : déploiement plus simple, mais peu de contrôle sur la redondance et impossible de provoquer une panne d'instance ; **une VM** : tout serait à construire à la main | Failover F1 à F3 (§ 6.4)                                                                            |
| Ne pas passer le projet à administrer des machines (P5)                                                   | **Autopilot** plutôt que GKE Standard                    | Google gère les nœuds ; facturation à la ressource demandée par les pods, pas à la machine                                                                                                | GKE Standard : nœuds à dimensionner et à mettre à jour nous-mêmes                                                                                                                  | Contrepartie mesurée : un pod qui exige une nouvelle machine met 5 min 29 s à servir                |
| Données dans l'UE, utilisateurs en France                                                                 | Région **europe-west9 (Paris)**                          | Hébergement UE (RGPD, P3) et latence réseau minimale depuis la France                                                                                                                        | Régions US, moins chères                                                                                                                                                              | —                                                                                                    |
| Construire l'image sans Docker sur nos postes                                                              | **Cloud Build**                                           | Construction dans le projet, à côté du dépôt d'images, reproductible                                                                                                                      | Docker local : dépend du poste, pousse 1 Go d'image depuis une connexion domestique                                                                                                    | —                                                                                                    |
| Un pod qui démarre vite et sans dépendance externe                                                       | **Modèle intégré à l'image**, Hugging Face hors ligne | Aucun téléchargement au démarrage, aucun service externe en production                                                                                                                      | Télécharger le modèle au démarrage : plus lent, et la production dépendrait de Hugging Face                                                                                        | Pod prêt en 15 à 20 s quand une machine est disponible (F2)                                         |
| Un calcul sur CPU, sans GPU                                                                                | **torch CPU**                                             | Notre inférence (8 ms) n'a pas besoin de GPU ; la version CPU évite ≈ 2 Go de bibliothèques CUDA inutiles                                                                                  | Nœuds GPU : coût sans rapport avec le besoin (P5)                                                                                                                                     | Le CPU est le goulot (≈ 4 req/s par pod), mais un GPU coûterait bien plus qu'un pod supplémentaire |
| Retirer du trafic un pod qui n'est pas prêt, redémarrer un pod bloqué                                   | **Trois sondes** sur `/health`                          | startup : laisse jusqu'à 5 min pour charger spaCy et le modèle ; readiness : pas de trafic avant d'être prêt ; liveness : redémarrage d'un pod figé                                      | Une seule sonde : un pod lent à démarrer serait tué en boucle                                                                                                                        | Remplacement immédiat en F1                                                                          |
| Ne pas gaspiller la mémoire du pod                                                                        | **Un seul worker uvicorn** (justification a posteriori)   | Chaque worker charge sa propre copie de spaCy et du modèle. Avec 1,43 Go au pic, deux workers dépasseraient les 2 Go ; et sur 1 CPU, un second worker n'apporte aucun calcul supplémentaire | 2 workers ou plus                                                                                                                                                                       | Mémoire mesurée (§ 7.1)                                                                            |

### 4.3 Dimensionnement : pourquoi 1 CPU par pod, et de 2 à 5 pods

Ces chiffres ont été posés **avant** les tests, sur des raisons de coût et de redondance, puis **confrontés aux mesures de l'étape 5** (P2). Les mesures les confirment pour l'usage prévu et fixent leur limite.

**Ce que vaut un pod.** Un pod à 1 CPU sert **≈ 4 requêtes/s** quand son CPU est saturé (91 à 99 %). Un utilisateur de nos tests envoie ≈ 1 requête/s (10 utilisateurs → 8 requêtes/s mesurées).

| Configuration                   | Capacité                                 | Utilisateurs servis avec P95 < 2 s                                                     | Source          |
| ------------------------------- | ----------------------------------------- | -------------------------------------------------------------------------------------- | --------------- |
| 1 pod (après une panne, F3)    | ≈ 4 req/s                                | 5 utilisateurs tenus de justesse (P95 1,09 s, maximum 4,7 s)                           | F3              |
| **2 pods (minimum)**      | **≈ 8 req/s**                      | **10 utilisateurs** (P95 1,2 s) ; rupture à 20                                  | Montée, stress |
| **5 pods (maximum)**      | 17 à 20 req/s mesurées                  | **≈ 20 utilisateurs**, par calcul (5 × 4 req/s) ; P95 non mesuré à ce palier | Montée         |
| 5 pods face à 100 utilisateurs | 17,6 req/s servies pour ≈ 100 demandées | × P95 11,8 s                                                                          | Montée         |

| Réglage              | Raison posée au départ                                                                                                                             | Ce que les mesures en disent                                                                                                                                                                                                          |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 CPU et 2 Go par pod | Autopilot facture les ressources demandées : 2 CPU et 4 Go étaient dimensionnés pour LAYA (421 M de paramètres), inutiles pour DistilBERT (66 M) | Mémoire au pic : 1,43 Go, soit ≈ 30 % de marge sur 2 Go. Le CPU est saturé : c'est lui qui justifie de raisonner en nombre de pods                                                                                                 |
| 2 pods minimum        | Redondance : un pod peut tomber sans couper le service                                                                                               | L'usage normal reste sous 2 req/s (référence de nos alertes) : 2 pods en servent 8, **marge × 4**. La perte d'un pod sur 2 a été tenue sans erreur (F3)                                                                    |
| 5 pods maximum        | Plafond de coût (crédits étudiants, P5)                                                                                                           | 5 pods à 1 CPU, plus Prometheus et Grafana, approchent le **quota de 12 CPU** du projet : c'est très probablement ce quota qui a bloqué un pod pendant F3 (§ 6.4). Monter plus haut demanderait d'abord une hausse de quota |
| Cible de 70 % de CPU  | Garder de la marge pour les pics                                                                                                                     | Un pod neuf met 5 min 29 s à servir. Pendant ce temps, les 30 % restants des pods en place absorbent la hausse (≈ 1,2 req/s par pod)                                                                                                |

**Conclusion.** 2 à 5 pods couvrent l'usage visé : l'usage normal avec une marge de 4, et un pic d'environ 20 utilisateurs actifs. **Ils ne couvrent pas 100 utilisateurs simultanés** : il faudrait au moins 25 pods à 1 CPU (100 req/s ÷ 4), donc un quota ou bien plus de CPU par pod et un traitement par lots (§ 6.5). C'est un choix assumé de coût, pas une capacité illimitée.

### 4.4 Utiliser l'API

Exemples **réels**, relevés le 16 novembre 2026 à 10:40 UTC (modèle `distilbert-2026-11-16`). `<domaine>` et `<CLE_API>` remplacent les vraies valeurs : le dépôt est public.

```
curl https://<domaine>.sslip.io/health
{"status":"ok"}

curl -X POST https://<domaine>.sslip.io/score \
  -H "Content-Type: application/json" -H "X-API-Key: <CLE_API>" \
  -d '{"text":"Thanks for fixing the references, great work."}'
{"toxique":false}

curl -X POST https://<domaine>.sslip.io/score ... -d '{"text":"You are a stupid idiot"}'
{"toxique":true}

curl https://<domaine>.sslip.io/health
{"status":"ok"}
```

| Cas                                                                 | Code                     | Origine                  |
| ------------------------------------------------------------------- | ------------------------ | ------------------------ |
| Clé absente ou fausse                                              | 401                      | Vérification de la clé |
| Texte vide, champ absent, plus de 5 000 caractères, corps non JSON | 422                      | Validation Pydantic      |
| Corps de plus de 40 Ko                                              | 413                      | Couche de protection     |
| Trop de requêtes, ou trop de clés fausses depuis une adresse      | 429                      | Couche de protection     |
| Plus de 3 calculs simultanés sur un pod pendant plus de 1 s        | 503 (`Retry-After: 1`) | Plafond de calcul        |

**API locale.** Une seconde API (`api/main_local.py`, route `/predire`, sans clé) sert au développement : elle permet de **choisir le modèle** (BiLSTM, DistilBERT ou LAYA) et renvoie le détail des étapes. Le front `front/index.html` s'appuie dessus (§ 9).

### 4.5 Structure du code et tests

| Dossier                         | Contenu                                                                                                                                                                                            |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `api/`                        | `main.py` (routes), `preprocessing.py` (anonymisation et nettoyage, même code qu'à l'entraînement), `scorer.py` (chargement du modèle et seuils), `protection.py` (limites en entrée) |
| `api/k8s/`                    | `deployment.yaml`, `service.yaml`, `ingress.yaml`, `hpa.yaml`, `podmonitor.yaml`                                                                                                         |
| `api/deploy/`                 | `gke_setup.sh` (mise en place, une fois), `deploy_gke.sh`, `gke_pause.sh` (pause pour économiser le crédit), `verifier_deploiement.py`                                                   |
| `api/tests/`                  | 26 fonctions pytest : clé, validation d'entrée, format de réponse, anonymisation, protection, vrai modèle                                                                                      |
| `loadtest/`, `supervision/` | Scripts Locust, résultats, tableau de bord Grafana, règles d'alerte, analyse des journaux                                                                                                        |

---

## 5. Sécurité et conformité RGPD (étape 4)

### 5.1 Analyse des risques (STRIDE)

Actifs à protéger : **les textes soumis** (données personnelles potentielles), **la clé d'API** (propriété intellectuelle), **la disponibilité du service**.

| Menace (STRIDE)                  | Scénario concret                                                     | Mesure en place                                                                                                                        | Statut                                                        |
| -------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **S**poofing               | Appeler l'API sans y avoir droit ; deviner la clé                    | Clé de 64 caractères hexadécimaux (`openssl rand -hex 32`), comparaison à temps constant, 429 après 10 clés fausses par minute | (clé unique partagée : )                                    |
| **T**ampering              | Déposer un exécutable dans le conteneur compromis ; image modifiée | `readOnlyRootFilesystem`, non-root, `drop ALL` ; image construite par Cloud Build, nœuds en lecture seule sur le dépôt d'images |                                                               |
| **R**epudiation            | Impossible de reconstituer une attaque                                | Journaux complets du load balancer, refus journalisés avec une empreinte HMAC de l'adresse                                            | (une seule clé : on ne sait pas quel client l'utilise)       |
| **I**nformation disclosure | Fuite des textes ; interception ; schéma de l'API exposé            | Texte jamais journalisé (prouvé, S5) ; HTTPS forcé ; `/docs` fermé ; réponse réduite ; poids hors de Git       | (HTTP non chiffré entre le load balancer et les pods : )     |
| **D**enial of service      | Inonder `/score`, qui coûte 100 à 250 ms de CPU                   | Limites par adresse par pod (429), au plus 3 calculs par pod (503), corps ≤ 40 Ko, délai de 15 s, autoscaler                         | limites par pod, pas globales ; Cloud Armor refusé par quota |
| **E**levation of privilege | Sortir du conteneur ; utiliser les droits du pod sur le projet        | `allowPrivilegeEscalation: false`, aucun rôle Google Cloud pour les pods                                                            |  (comptes humains `Owner` : § 5.3)                       |

**Rattachement aux référentiels.**

- **OWASP API Security Top 10 (2023)** : API2 Broken Authentication → clé à temps constant et anti brute-force ; API4 Unrestricted Resource Consumption → limites, plafond de calcul, 413 ; API8 Security Misconfiguration → `/docs` fermé, en-tête `Server` retiré, conteneur durci ; API9 Improper Inventory Management → une seule route métier exposée (`/score`).
- **CIS Kubernetes / GKE Benchmark** : conteneur non-root, pas d'élévation de privilèges, capacités retirées, système de fichiers en lecture seule, secrets hors de l'image.
- **ANSSI**, recommandations pour un déploiement sécurisé : moindre privilège, cloisonnement (métriques sur un port non exposé), journalisation.

### 5.2 Authentification, chiffrement, validation

| Besoin                                                                | Choix                                                                                              | Raison technique                                                                                                                                                                     | Alternative écartée                                                                                                                                                              | Preuve                                       |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| Réserver l'API à des clients connus                                 | **Clé d'API** dans l'en-tête `X-API-Key`, comparée à temps constant                    | Un appel = une vérification, sans état ni serveur d'identité. Le temps constant empêche de deviner la clé caractère par caractère en mesurant le temps de réponse            | **JWT** : utile pour des sessions d'utilisateurs avec expiration et droits variables ; ici, il ajouterait un émetteur de jetons et une rotation sans rien protéger de plus | S1, S2 : 401                                 |
| Chiffrer le trafic sans gérer de certificat                          | **Certificat géré par Google** sur l'Ingress, domaine `<ip>.sslip.io`                    | Émission et renouvellement automatiques ; sslip.io donne un nom de domaine gratuit pointant vers notre IP, condition pour obtenir le certificat                                     | Certificat manuel (Let's Encrypt) : renouvellement à surveiller ; acheter un domaine (P5)                                                                                         | S3 : 301 vers HTTPS                          |
| Rejeter les entrées invalides avant tout calcul                      | **Pydantic** : 1 à 5 000 caractères, sinon 422                                             | Validation déclarative, intégrée à FastAPI, avant le NER et le modèle                                                                                                           | Contrôles écrits à la main dans la route                                                                                                                                        | S4 : 422                                     |
| Laisser le front de démonstration appeler l'API depuis un navigateur | **CORS ouvert à toutes les origines, sans cookies**. GET et POST, deux en-têtes autorisés | La clé est dans un en-tête, jamais dans un cookie : une page tierce ne peut pas l'utiliser à l'insu de l'utilisateur, donc ouvrir les origines n'affaiblit pas l'authentification | Liste blanche d'origines : impossible, le front est ouvert depuis un fichier (origine `null`)                                                                                    | Front en mode « API distante » fonctionnel |
| Clé hors du code, du dépôt public et de l'image                    | **Secret Manager** → **Secret Kubernetes** → variable d'environnement                | Accès contrôlé par IAM et journalisé ; la clé change sans reconstruire l'image                                                                                                  | Variable écrite dans le manifeste ou le code : elle finirait dans Git (c'est arrivé une fois dans une branche, clé révoquée depuis)                                           | `gke_setup.sh`, étape 3/6                 |

**Réglages de la protection en entrée : d'où viennent les chiffres (P2, P4).** Ces seuils ne sont pas arbitraires : ils dérivent de la capacité mesurée : ≈ 4 calculs/s par pod saturé, soit ≈ 250 ms de CPU par calcul sous charge.

| Réglage                              | Valeur                            | Raison                                                                                                                                                                 |
| ------------------------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Calculs simultanés par pod           | 3, attente maximale 1 s, puis 503 | 3 calculs × ≈ 250 ms + 1 s d'attente au plus : une requête acceptée reste sous le critère de 2 s. Au-delà, mieux vaut un refus immédiat qu'une réponse en 30 s |
| `/score` par adresse et par pod     | 60 par minute                     | Un usage normal est ≈ 1 requête/s. La limite est volontairement large, parce que tout le wifi de l'école sort par une seule adresse                                 |
| Toutes routes, par adresse et par pod | 300 par minute                    | Freine une inondation de pages légères, comme celle du 16 novembre (191 req/s sur `/docs`)                                                                         |
| Clés fausses par adresse             | 10 par minute, puis 429           | Un client légitime ne se trompe pas de clé 10 fois en une minute ; un brute-force, si                                                                                |
| Taille du corps                       | 40 Ko, puis 413                   | 5 000 caractères accentués font ≈ 10 Ko ; le reste est une marge pour le JSON. Au-delà, ce n'est plus un commentaire                                               |
| Délai du load balancer               | 15 s (30 s par défaut)           | Un score prend ≈ 0,1 s : une requête qui traîne 15 s est anormale et occupe une connexion pour rien                                                                 |

Tous ces réglages sont des variables d'environnement : on les ajuste sans reconstruire l'image.

**Défaut connu.** Une clé contenant un caractère non ASCII provoque une **erreur 500 au lieu de 401** (S2b) : `compare_digest` refuse de comparer des chaînes (`TypeError`). Il est toujours présent dans le code en service (`api/main.py`). Correction : comparer des octets, `compare_digest(cle.encode(), API_KEY.encode())`.

### 5.3 Moindre privilège et droits d'accès (IAM)

**Ce qui applique le moindre privilège, avec sa preuve :**

| Compte ou composant                   | Droits                                                                                     | Pourquoi c'est le minimum                                                                           | Preuve                                                       |
| ------------------------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| **Pods de l'API**               | **Aucun rôle Google Cloud**                                                         | L'API n'appelle aucun service Google : une faille dans le conteneur ne donne aucun accès au projet | Aucun compte de service dédié ni liaison IAM pour les pods |
| **Nœuds du cluster**           | `artifactregistry.reader` sur le seul dépôt d'images `dss`, pas sur le projet        | Ils n'ont besoin que de télécharger l'image                                                       | `gke_setup.sh`, étape 5/6 (extrait ci-dessous)            |
| **Processus dans le conteneur** | uid 1000, aucune capacité Linux, pas d'élévation, système de fichiers en lecture seule | Le moindre privilège s'applique aussi à l'intérieur du pod                                       | `deployment.yaml` (§ 4.2)                                 |
| **Secret de la clé**           | Un seul administrateur du secret (Enzo)                                                    | Limite qui peut changer la clé                                                                     | Relevé IAM                                                  |
| **Poids du modèle**            | Bucket privé, lecture seule pour la chaîne de livraison                                  | Seul ce qui construit l'image peut le lire                                                          | Configuration du bucket                                      |
| **Métriques**                  | Port 9090, ni dans le Service ni dans l'Ingress                                            | Lisibles par Prometheus dans le cluster, pas depuis Internet                                        | `deployment.yaml`, `service.yaml`                        |

**Ce qui ne l'applique pas pleinement, et l'état cible :**

| Qui    | Rôles actuels                                                                                                        | État cible                                                                                            |
| ------ | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Enzo   | `Owner` + 8 rôles précis (artifactregistry.writer, cloudbuild.editor, container.developer, secretmanager.admin…) | Retirer `Owner` ; garder les 8 rôles précis qui couvrent exactement ses besoins                    |
| Situ   | `Owner` + container.developer, logging.viewer, monitoring.viewer                                                    | Retirer `Owner` ; garder container.developer, logging.viewer, monitoring.viewer                      |
| Eliana | `Owner`                                                                                                             | Conserve `Owner` : crée le projet, gère le budget et la facturation (accès billing indispensable) |

- **Conséquence concrète (état actuel)** : Enzo et Situ peuvent supprimer le cluster, modifier les droits des autres et **lire la clé d'API**. Leurs rôles précis sont redondants avec `Owner`.
- **Pourquoi pas encore corrigé** : commodité d'un projet étudiant ; sera corrigé en fin de TP.
- **Cible en production** : un seul `Owner` (Eliana) ; des groupes plutôt que des comptes nominatifs ; la double authentification imposée par une politique d'organisation ; un compte de service dédié aux nœuds.

**Bilan : le moindre privilège est respecté pour tous les comptes machines et à l'intérieur du conteneur. Pour les comptes humains, il sera appliqué en fin de TP (retrait du rôle `Owner` d'Enzo et Situ).**

### 5.4 Journaux et RGPD

- **Journaux de l'API** : une ligne par analyse, `score=60 longueur=67 duree_ms=80.2`. Jamais le texte, jamais l'adresse (`--no-access-log`).
- **Refus** (401, 429, 503) : motif, route et **empreinte HMAC de 10 caractères** de l'adresse (clé secrète du serveur), au plus une ligne par minute et par client. On peut reconnaître un client sans le nommer.
- **Journaux du load balancer** : adresse IP, chemin, code, outil. Activés volontairement (`sampleRate: 1.0`), car ce sont les seuls à permettre de reconstituer une attaque (§ 7.4). **Ils contiennent des adresses IP, donc des données personnelles** : déclarés dans le registre, conservés 30 jours.
- **Preuve (test S5)** : envoi de « Bonjour je suis Jean Dupont, ip 192.168.45.67, mot-test ZEBRAXYZ123 », puis recherche de ces trois éléments dans Cloud Logging sur 30 minutes : **aucun résultat**.

### 5.5 Registre de traitement (article 30) : synthèse

Le registre complet et corrigé est dans le dossier `01_registre_RGPD`. Il distingue deux traitements.

| Rubrique     | A. Préparation du jeu d'entraînement                                                                | B. API de score en service                                                                             |
| ------------ | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Finalité    | Réduire les données personnelles avant l'entraînement (cadre pédagogique)                         | Fournir un score de toxicité de 0 à 100                                                              |
| Base légale | Intérêt légitime (art. 6.1.f) ; commentaires publics, sous licence                                 | Intérêt légitime (art. 6.1.f), mis en balance par la minimisation                                   |
| Données     | Texte libre (noms, pseudos, IP, e-mails…) ; labels pouvant révéler des attaques contre des groupes | Texte soumis (en mémoire seulement) ; score, longueur, durée ; IP dans les journaux du load balancer |
| Conservation | Fichiers anonymisés supprimés après la notation                                                    | Texte : aucune ; journaux : 30 jours                                                                   |
| Hors UE      | Le dépôt GitHub (États-Unis) contient le **jeu brut public**                                 | Le calcul et les journaux en UE ; la police du front de démonstration vient de Google Fonts           |

**Décision automatisée (art. 22).** Le score ne doit jamais être la seule base d'une décision à effet juridique. S'il servait à modérer ou à refuser un accès, une analyse d'impact (AIPD, art. 35) serait obligatoire.

---

## 6. Montée en charge (étape 5)

### 6.1 Méthode

| Choix                                                                                                             | Justification                                                                                                                                                                                                                                                                                                          |
| ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Locust                                                                                                            | Les scénarios sont du code Python, comme le reste du projet : c'est ce qui a permis l'arrêt automatique du stress test et l'attaque mêlée au trafic légitime. **Apache Bench** ne sait pas envoyer qu'une même requête en boucle ; **k6** s'écrit en JavaScript, une langue de plus dans le projet |
| Cible : l'API sur GKE, pas l'API locale                                                                           | On teste aussi le load balancer, l'autoscaler et les pods                                                                                                                                                                                                                                                              |
| 1 000 textes réels de `test_clean.csv`, un différent à chaque requête                                       | Textes réalistes ; aucun cache ne fausse la mesure                                                                                                                                                                                                                                                                    |
| Percentiles recalculés requête par requête (`*_requetes.csv`)                                                | Ceux de Locust sont cumulés depuis le début du test : inutilisables par palier                                                                                                                                                                                                                                       |
| Seuil de rupture : P95 > 2 s                                                                                      | Choix de l'équipe : au-delà, un appel interactif est jugé trop lent                                                                                                                                                                                                                                                 |
| Stress : +10 utilisateurs toutes les 20 s, **arrêt automatique** dès que le P95 dépasse 2 s pendant 10 s | Critère mesurable, et le test s'arrête seul pour économiser le crédit                                                                                                                                                                                                                                              |

**Conditions.** Mesures du 12 novembre, à 1 CPU et 2 Go par pod (ReplicaSet `69798c4847`, vérifié actif pendant tous les tests). Ces mesures sont antérieures à la couche de protection déployée le 16 novembre : avec la limite actuelle (60 `/score` par adresse par minute), un Locust lancé depuis une seule machine recevrait des 429. Locust tournait sur un Mac : les latences incluent le réseau.

### 6.2 Montée progressive (1 → 10 → 50 → 100 utilisateurs en 5 min)

| Palier | Requêtes/s | Moyenne | Médiane | P95    | P99    | Erreurs |
| ------ | ----------- | ------- | -------- | ------ | ------ | ------- |
| 1      | 0,9         | 317 ms  | 176 ms   | 992 ms | 1,3 s  | 0       |
| 10     | 8,0         | 482 ms  | 384 ms   | 1,2 s  | 1,6 s  | 0       |
| 50     | 14,2        | 2,8 s   | 1,6 s    | 8,2 s  | 11,2 s | 1       |
| 100    | 17,6        | 4,9 s   | 4,1 s    | 11,8 s | 14,7 s | 2       |

- **L'API ne tombe pas, elle ralentit** : 4 erreurs 502 sur 3 616 requêtes (≈ 0,1 %), mais une latence médiane qui passe de 176 ms à plus de 4 s. Les requêtes font la queue.
- **Le goulot est le CPU** : pods à 91-99 % de leur CPU, ≈ 4 requêtes/s par pod.
- **L'autoscaler est trop lent pour un pic de 5 minutes** : un pod neuf a mis 5 min 29 s à être prêt, dont 5 min 10 s en attente d'une machine. Une première exécution est restée à 8 requêtes/s ; la seconde a atteint 5 pods et 17 à 20 requêtes/s.

### 6.3 Stress test

Rupture (P95 > 2 s) **à 20 utilisateurs, 33 s après le début**, pour un débit maximal de ≈ 8 requêtes/s avec 2 pods, soit ≈ 4 par pod. **0 erreur** : c'est une dégradation, pas une panne. Le test est trop court pour que l'autoscaler réagisse : c'est la capacité de la configuration de départ.

### 6.4 Failover

| Test | Scénario                                                                       | Résultat                                                                                 |
| ---- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| F1   | Suppression propre d'un pod (`kubectl delete`), 5 utilisateurs, 5 pods prêts | 0 erreur sur 1 192 requêtes ; P95 628 ms avant, 465 ms après                            |
| F2   | Arrêt brutal (`--grace-period=0 --force`), mêmes conditions                 | 1 erreur sur 771 (un 502 du load balancer, 2 s après) ; débit en baisse pendant ≈ 10 s |
| F3   | **Pire cas** : arrêt brutal avec seulement **2 pods**              | 0 erreur sur 892 ; **un seul pod pendant 7 min 27 s** ; P95 779 → 1 092 ms         |

**Ce que F3 a révélé.** Le pod de remplacement est resté en attente : Google a refusé d'ajouter une machine (`GCE quota exceeded`). Le plus serré des quotas relevés ensuite est la limite globale du projet, **12 CPU toutes régions confondues** (4/12 hors charge). Hypothèse la plus plausible, non vérifiable après coup : elle a été atteinte quand l'API, Prometheus et Grafana occupaient le plus de machines. 

**Le risque n'est donc pas Kubernetes, mais la capacité que Google accepte de fournir.** Par ailleurs, le pod survivant a lui-même été arrêté pendant l'incident : aucun `PodDisruptionBudget` ne l'empêchait.

### 6.5 Améliorations proposées, reliées aux mesures

| Priorité | Amélioration                                                      | État                                                                                               | Mesure qui la justifie                                                                    |
| --------- | ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 1         | 3 pods minimum et un `PodDisruptionBudget` (`minAvailable: 1`) | Proposée                                                                                           | F3 : 7 min 27 s sur un seul pod, et le survivant évincé                                 |
| 2         | Refuser tôt plutôt que faire attendre                            | **Faite le 16/11** : 429 par adresse, 54 × 503, `/health` toujours 200, aucun redémarrage | 80 requêtes simultanées : 26 × 200, 54 × 503, `/health` toujours 200                |
| 3         | Plus de CPU par pod, ou réglage des threads de torch              | Proposée                                                                                           | Pods saturés à 91-99 % pour ≈ 4 requêtes/s                                            |
| 4         | Traitement par lots                                                | Proposée                                                                                           | Le modèle est plus efficace par lots ; un appel par commentaire pèse à 100 requêtes/s |
| 5         | Monter le minimum de pods avant un pic annoncé                    | Proposée                                                                                           | 5 min 29 s pour qu'un pod neuf serve                                                      |
| 6         | Limite globale (Cloud Armor ou Redis)                              | **Essayée, refusée** : quota `SECURITY_POLICIES` à 0 sur le projet étudiant             | Les limites actuelles sont par pod ; avec 5 pods, la limite réelle est 5 fois plus haute |
| 7         | File d'attente pour les pics                                       | Proposée                                                                                           | Absorbe un pic sans bloquer l'appelant                                                    |
| 8         | Cache des textes déjà vus                                        | Proposée, **non mesurée**                                                                   | Nos tests envoient un texte différent à chaque requête                                 |
| —        | Load balancer et redondance (2 pods minimum)                       | **En place et testés**                                                                       | F1 : 0 erreur                                                                             |
| —        | Modèle plus léger (BiLSTM, 0,13 ms)                              | Écartée                                                                                           | F1 de 0,36 contre 0,56 : nous préférons la qualité                                     |

---

## 7. Supervision, alertes et incidents (étape 6)

### 7.1 Prometheus et Grafana

- **Installation dans le cluster** (Helm, `kube-prometheus-stack`) plutôt qu'en service géré : ce sont les outils demandés par le sujet, sans offre payante en plus.
- **Métriques sur un port séparé (9090)**, non relié au Service ni à l'Ingress : contrairement à un `/metrics` sur le port public, elles ne sont pas lisibles depuis Internet. Prometheus les lit sur le pod (PodMonitor).
- **Grafana sans adresse publique** : on l'ouvre par `port-forward`.
- **Tableau de bord conçu par nous** (`grafana_dashboard.json`, importable). Les tableaux de bord Kubernetes livrés avec Grafana restent vides (« No data ») : GKE Autopilot ne laisse pas Prometheus lire les métriques kubelet. Nous nous appuyons donc sur les métriques exposées par l'API elle-même.

**Métriques exposées et pourquoi :**

| Métrique                                                                | Question à laquelle elle répond                                                                                             |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| Requêtes/s par route et par code                                        | Le trafic est-il normal ? Sur quelle route arrive une attaque ?                                                               |
| Part de 4xx et de 5xx                                                    | Les clients se trompent-ils ? Le service casse-t-il ?                                                                         |
| `dss_refus_total` par motif (clé invalide, débit, surcharge, taille) | La protection travaille-t-elle, et contre quoi ?                                                                              |
| Latence P95 de `/score`                                                | Que vivent presque tous les utilisateurs ? (intervalles élargis jusqu'à 10 s le 16/11 ; avant, la courbe plafonnait à 1 s) |
| CPU et mémoire par pod                                                  | Où est le goulot ? (le CPU, pas la mémoire)                                                                                 |
| Pods prêts / réplicas voulus                                           | La redondance promise est-elle là ?                                                                                          |

### 7.2 Alertes

Le sujet demande une API « observable et auditable (logs, métriques, alertes) ». Depuis le 16 novembre, **7 règles Prometheus** (`supervision/alertes.yaml`) :

| Alerte              | Condition                                           | Pourquoi ce seuil                                                                                                     | Sévérité   |
| ------------------- | --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------- |
| DssDebitAnormal     | Plus de 30 requêtes/s pendant 1 min                | 15 fois l'usage normal (< 2/s) et près de 4 fois la capacité de calcul (≈ 8/s) : impossible sans abus              | critique      |
| DssRefusEnHausse    | Plus de 1 refus/s pendant 2 min, par motif          | Un client légitime n'est presque jamais refusé ; un refus par seconde est une tentative ou un client mal configuré | avertissement |
| DssClesFausses      | Plus de 0,2 clé fausse/s sur 5 min                 | Une erreur de saisie isolée ne déclenche rien ; 60 clés fausses en 5 min, si                                       | avertissement |
| DssErreurs5xx       | Plus de 5 % de réponses 5xx                        | Le service casse vraiment, au-delà des erreurs ponctuelles (0,1 % mesuré sous forte charge)                         | critique      |
| DssLatenceP95       | P95 de `/score` au-dessus de 2 s                  | Notre critère de rupture de l'étape 5                                                                               | critique      |
| DssPodsInsuffisants | Moins de 2 pods prêts                              | La redondance minimale n'est plus là (cas F3)                                                                        | critique      |
| DssRedemarrages     | Un pod a redémarré dans les 10 dernières minutes | Un redémarrage révèle une panne (mémoire, blocage) que la sonde a dû corriger                                    | avertissement |

**Limite assumée** : Alertmanager n'est pas installé (retiré pour libérer de la mémoire, et aucun canal de notification n'était configuré). Une alerte se lit dans Prometheus ou Grafana, mais elle n'envoie aucun message.

### 7.3 Tests de sécurité

| ID  | Test                                                                                       | Attendu          | Résultat                                                                                                  |
| --- | ------------------------------------------------------------------------------------------ | ---------------- | ---------------------------------------------------------------------------------------------------------- |
| S1  | `/score` sans clé                                                                       | 401              | 401                                                                                                        |
| S2  | Mauvaise clé                                                                              | 401              | 401                                                                                                        |
| S2b | Clé avec un caractère non ASCII                                                          | 401              | **500** (bogue, § 5.2)                                                                              |
| S3  | Appel en HTTP                                                                              | redirection      | 301 vers HTTPS                                                                                             |
| S4  | Texte vide, > 5 000 caractères, corps non JSON                                            | 422              | 422                                                                                                        |
| S5  | Le texte reçu n'apparaît pas dans les journaux                                           | aucun résultat  | aucun résultat (canari ZEBRAXYZ123)                                                                       |
| S6  | `/docs` sans clé                                                                        | à décider      | 200 au 12/11 → **404 depuis le 16/11**                                                             |
| S7  | Rafale invalide (8 attaquants) **pendant que 2 utilisateurs légitimes travaillent** | service maintenu | 5 812 requêtes d'attaque toutes refusées (401/422, médiane 25 ms) ; légitimes : 0 erreur, P95 170 ms   |
| S8  | Limitation de débit                                                                       | 429              | aucun 429 au 12/11 → **en service le 16/11** : 150 requêtes à la suite, 106 × 200 et 44 × 429  |
| S9  | Brute-force de la clé                                                                     | blocage          | 30 clés fausses : 16 × 401 puis 14 × 429                                                                |

### 7.4 Incident réel I-001 : l'attaque du 16 novembre

Le 16 novembre, l'API a reçu 94 161 requêtes hostiles en moins de deux heures. L'incident a été détecté grâce à Grafana et analysé via les journaux du load balancer. L'attaque, sa reconstruction et les défenses déployées en réponse font l'objet du rapport TP2.

---

## 8. Architecture cloud (étape 7)

### 8.1 Schéma

| Repère | Signification                                                                                     |
| ------- | ------------------------------------------------------------------------------------------------- |
| 1 → 4  | Trajet d'une requête : client → load balancer HTTPS → Service → pod → réponse               |
| a → g  | Dans le pod : protection, clé, validation, anonymisation, nettoyage, DistilBERT, seuils et score |
| A       | Secret Manager → Secret Kubernetes → variable d'environnement `API_KEY`                       |
| B       | Artifact Registry → nœuds (lecture seule, sur ce dépôt d'images seulement)                    |
| C       | Journaux de l'API → Cloud Logging (jamais le texte)                                              |
| D       | Journaux du load balancer → Cloud Logging (adresse IP, 30 jours)                                 |
| Orange  | Supervision dans le cluster ; métriques par le port 9090, non public                             |

### 8.2 Texte explicatif

L'infrastructure repose sur **GKE Autopilot en région europe-west9 (Paris)** : le calcul et les journaux restent dans l'Union européenne. Il n'y a **qu'un seul point d'entrée public**, le load balancer HTTPS de Google. Il porte un certificat géré, redirige le HTTP vers le HTTPS, coupe les requêtes au bout de 15 s et journalise chaque appel. Il répartit le trafic entre les seuls pods **prêts**, via un Service interne.

Chaque pod suit les étapes a → g. Les refus bon marché (429, 413, 503, 401, 422) arrivent **avant** les traitements coûteux. Le texte est anonymisé **avant** le modèle, et n'est jamais écrit sur le disque ni dans les journaux. Le pod ne possède aucun droit sur le projet Google Cloud. Son système de fichiers est en lecture seule, et seuls deux petits volumes en mémoire sont inscriptibles.

L'autoscaler maintient 2 à 5 pods à 70 % de CPU. Il absorbe une charge durable, mais pas un pic de quelques minutes (§ 6).

### 8.3 Flux, authentification et chiffrement

| Flux                                  | Chiffrement                                        | Authentification                     |
| ------------------------------------- | -------------------------------------------------- | ------------------------------------ |
| 1. Client → load balancer            | HTTPS (certificat Google), HTTP redirigé          | Aucune à ce niveau                  |
| 2-3. Load balancer → Service → pods | **HTTP, réseau interne Google, pas de TLS** | Aucune à ce niveau                  |
| Dans le pod                           | Mémoire seulement                                 | Clé `X-API-Key` à temps constant |
| 4. Réponse                           | HTTPS                                              | —                                   |
| A. Secret → pods                     | Secret Kubernetes                                  | Droits Kubernetes                    |
| B. Image → nœuds                    | Réseau interne Google                             | Lecture seule sur ce dépôt         |
| C, D. Journaux                        | Réseau interne Google                             | Service géré                       |

### 8.4 Approche zero trust

| Principe                                | Appliqué                                                                                              | Manque                                                                                      |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| Ne jamais faire confiance au réseau    | Chaque appel à `/score` est authentifié, même venant de l'intérieur                              | Pas de TLS entre le load balancer et les pods ; pas de `NetworkPolicy`                    |
| Moindre privilège                      | Pods sans rôle, nœuds en lecture seule, conteneur durci (§ 5.3)                                     | Deux comptes humains avec `Owner` superflus (Enzo et Situ, à corriger en fin de TP)  |
| Vérifier explicitement chaque appelant | Clé obligatoire, anti brute-force                                                                     | **Une seule clé partagée** : impossible d'identifier ou de révoquer un client seul |
| Réduire la surface                     | `/docs` fermé, `/health` muette, `/version` réservée à la clé, en-tête `Server` retirée | —                                                                                          |
| Supposer la compromission               | Système de fichiers en lecture seule, journaux du load balancer, alertes                              | Pas de WAF (Cloud Armor refusé par quota)                                                  |

### 8.5 Index des choix techniques


| Choix                                                                | Principe                             | Justifié en  |
| -------------------------------------------------------------------- | ------------------------------------ | ------------- |
| Regex + spaCy `en_core_web_sm`, traitement local                   | P1, P3, P2                           | § 2.2        |
| Jeu Jigsaw plutôt que GameTox                                       | P2                                   | § 2.1        |
| DistilBERT déployé ; BiLSTM et LAYA comparés                      | P2, P5                               | § 3.2 à 3.4 |
| Score = moyenne des labels détectés                                | —                                   | § 3.5        |
| GKE Autopilot à Paris, Cloud Build, modèle dans l'image, torch CPU | P5, P3                               | § 4.2        |
| 1 CPU par pod, 2 à 5 pods, cible de 70 %                            | P2, P5                               | § 4.3        |
| Clé d'API, certificat géré, Secret Manager, Pydantic, CORS        | P4                                   | § 5.2        |
| Seuils de la protection (3 calculs, 60/min, 40 Ko…)                 | P2, P4                               | § 5.2        |
| Moindre privilège des comptes machines                              | P3                                   | § 5.3        |
| Journaux du load balancer conservés malgré les IP                  | P3 mis en balance avec la sécurité | § 5.4        |
| Locust, P95 comme critère, arrêt automatique                       | P2, P5                               | § 6.1        |
| Prometheus et Grafana dans le cluster, port 9090 interne             | P5, P4                               | § 7.1        |
| Seuils des alertes                                                   | P2                                   | § 7.2        |

---

## 9. Originalité et curiosité technique

**1. Des scénarios de charge pensés pour mesurer juste.**

- Un stress test qui **s'arrête seul** au premier critère de rupture (P95 > 2 s pendant 10 s, ou 5 erreurs en 10 s), pour économiser le crédit.
- Des **percentiles recalculés requête par requête**, parce que ceux de Locust sont cumulés depuis le début du test et faux par palier.
- Une **attaque mêlée à du trafic légitime** (S7), pour mesurer ce que vit l'utilisateur honnête pendant une attaque, et pas seulement si l'attaque échoue.
- Le **pire cas de failover** (F3, 2 pods), qui a fait apparaître une limite que personne n'attendait : le quota de machines de Google.

**2. Des preuves plutôt que des affirmations.**

- **Canari dans les journaux** : un mot unique (ZEBRAXYZ123) envoyé puis recherché, pour prouver que le texte n'est jamais journalisé.
- **Contrôle de la version du modèle** après déploiement, né d'un incident réel (le modèle factice du 13 novembre).

**3. Une supervision qui ne s'expose pas.** Métriques sur un port interne, Grafana sans adresse publique, tableau de bord conçu par nous quand ceux livrés par défaut restaient vides sur Autopilot.

**4. Un front de démonstration pédagogique.** `front/index.html` est une page unique, sans installation. Elle permet de choisir le modèle (BiLSTM, DistilBERT, LAYA) et montre le texte original, puis anonymisé, puis nettoyé, avec la durée de chaque étape. Une version « Pipeline » animée rejoue la vraie réponse étape par étape. L'historique ne garde que le texte **anonymisé**, et il est effacé à la fermeture de l'onglet.

**5. Un mode de calcul du score pensé pour ne pas tromper.** Le score de 0 à 100 n'est pas la moyenne des 6 probabilités : il est la **moyenne des seuls labels déclenchés** (ceux qui dépassent leur seuil). Un commentaire très toxique sur un seul label obtient 95, pas 16 (95 ÷ 6). Si aucun label n'est déclenché, on retombe sur la probabilité brute de `toxic`, pour ne jamais renvoyer 0 sur un texte ambigu. Ce choix est motivé par le déséquilibre des classes : les 5 labels minoritaires tireraient systématiquement le score vers le bas sans rien apporter à la décision.

**6. Un audit sans complaisance.** L'audit IAM juge chaque compte, y compris les nôtres. Le registre RGPD a été relu contre le code : 7 incohérences trouvées et corrigées. Le bogue S2b a été trouvé par nos propres tests.

---

## 10. Limites, risques résiduels et améliorations priorisées

| Priorité | Risque résiduel                                                           | Amélioration                                                                         | Effort |
| --------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ------ |
| 1         | Deux comptes `Owner` superflus (Enzo et Situ) : peuvent lire la clé ou supprimer le cluster | Retirer `Owner` à Enzo et Situ, garder leurs rôles précis ; Eliana conserve `Owner` (facturation) | Faible |
| 2         | Clé non ASCII → 500 (S2b)                                                | Comparer des octets (une ligne)                                                       | Faible |
| 3         | Une seule clé partagée                                                   | Une clé par client, stockée sous forme de hash ; changer la clé après la notation | Moyen  |
| 4         | Jeu brut public dans Git                                                   | Retirer `data/*.csv` de l'historique, documenter le téléchargement depuis Kaggle  | Faible |
| 5         | Reprise lente et dépendante du quota (F3)                                 | 3 pods minimum, `PodDisruptionBudget`, demande de quota                             | Faible |
| 6         | Limites par pod, pas globales                                              | Cloud Armor (si quota) ou Redis                                                       | Moyen  |
| 7         | Pas de TLS ni de `NetworkPolicy` dans le cluster                         | `NetworkPolicy` « seul le load balancer parle aux pods » ; mTLS                   | Moyen  |
| 8         | Alertes sans notification                                                  | Alertmanager vers un canal de l'équipe                                               | Faible |
| 9         | Anonymisation non mesurée                                                 | Annoter 500 commentaires à la main pour mesurer précision et rappel                 | Moyen  |
| 10        | Tests de charge antérieurs à la protection                               | Les relancer depuis plusieurs adresses                                                | Moyen  |

---

## 11. Conclusion

L'API répond au sujet. Elle détecte la toxicité avec un modèle choisi sur mesures (DistilBERT, F1 0,558), renvoie un score de 0 à 100, anonymise le texte avant le modèle et ne le garde jamais. Elle tourne en HTTPS dans l'UE, derrière une clé, dans un conteneur durci, sur 2 à 5 pods supervisés et alertés.

Nos tests en ont fixé les limites : environ 4 requêtes/s par pod, un autoscaler trop lent pour un pic, une reprise qui dépend du quota de Google. L'attaque réelle du 16 novembre a montré la différence entre une défense écrite et une défense en service. Elle a été le meilleur test de notre supervision, et le point de départ de la plupart de nos corrections.

**Face à l'objectif « de quelques utilisateurs à des milliers sans rupture ».** Aujourd'hui, l'API sert 10 à 20 utilisateurs actifs avec moins de 2 s de latence (§ 4.3) : l'objectif n'est pas atteint en volume. Le passage aux milliers est pourtant prévu par la conception. Les pods sont identiques et sans état, derrière un load balancer : on augmente la capacité en ajoutant des pods, sans rien réécrire. Pour 1 000 utilisateurs qui envoient un commentaire toutes les 10 s (100 requêtes/s), il faudrait ≈ 25 pods à la capacité actuelle, ou moins après deux optimisations à mesurer : le traitement par lots et 2 CPU par pod. Dans tous les cas, il faudrait aussi relever le minimum de pods avant un pic connu et augmenter le quota du projet. **Ce qui nous limite, c'est le budget et le quota de 12 CPU.**

Les faiblesses qui restent sont connues, mesurées et classées. Les plus importantes (comptes `Owner`, clé unique, bogue S2b) seront corrigés.

---

## Annexe A — Reproduire

```bash
# Environnement
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt    # inclut spaCy en_core_web_sm

# Données et modèles (le jeu Kaggle va dans data/)
# 1. notebooks/anonyme_2.ipynb    (~20 min)    -> data/anonymise/
# 2. notebooks/clean_text.ipynb                -> data/clean/
# 3. notebooks/train.ipynb    (BiLSTM ~3 min, DistilBERT ~64 min, LAYA ~2 h) -> models/

# API locale et front
.venv/bin/uvicorn api.main_local:app --port 8000    # API locale + front, http://127.0.0.1:8000/

# Mise en place GCP (une fois), puis déploiement
PROJECT_ID=<projet> bash api/deploy/gke_setup.sh
python api/export_model.py --type distilbert
PROJECT_ID=<projet> bash api/deploy/deploy_gke.sh
curl https://<domaine>.sslip.io/version -H "X-API-Key: <CLE_API>"    # jamais dummy-...

# Tests
cd api && pytest -v
export API_KEY=<clé>    # jamais dans un fichier
LOG_REQUETES=loadtest/results/montee_requetes.csv .venv/bin/locust \
  -f loadtest/locustfile.py,loadtest/montee.py --host https://<domaine>.sslip.io
.venv/bin/python loadtest/report.py montee
```

---

## Annexe B — Grille de tests complète et rapport de charge

La grille complète (sécurité S1 à S9, supervision SU1 à SU9, stress ST1 à ST4, failover F1 à F3b) est dans `supervision/GRILLE_TESTS.md`. Le rapport de charge détaillé (méthode, deux exécutions de la montée, autoscaling, failover, limites) est dans `loadtest/RAPPORT.md`, avec les CSV bruts et les scripts.

| Test non réalisé                         | Pourquoi                                                                    |
| ------------------------------------------ | --------------------------------------------------------------------------- |
| ST4 : rupture « dure » (vague d'erreurs) | Non atteinte jusqu'à 100 utilisateurs ; monter plus haut coûte du crédit |
| F4 : perte d'un nœud entier               | Non réalisé : sur Autopilot, les nœuds sont gérés par Google           |
