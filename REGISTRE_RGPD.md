# Registre des activités de traitement — Art. 30 RGPD

**Référence** : DSS-RGPD-2026-001
**Version** : 1.0
**Date de création** : 12 novembre 2026
**Statut** : En vigueur

---

## 1. Responsable du traitement

| Champ         | Valeur                        |
| ------------- | ----------------------------- |
| Dénomination | Équipe Digital Social Score                    |
| Projet        | Digital Social Score API — analyse de toxicité |
| Contact       | contact@digitalsocialscore.fr                  |
| Localisation  | France                                         |

---

## 2. Description du traitement

| Champ                              | Valeur                                                                                                                                                                                                                                                                                                                        |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Nom du traitement                  | Digital Social Score API — Analyse automatisée de toxicité                                                                                                                                                                                                                                                                 |
| Finalité principale               | Fournir une plateforme d'analyse automatisée de la toxicité de commentaires en ligne, restituant un score de 0 à 100 et une ventilation par catégorie de risque (toxic, severe_toxic, obscene, threat, insult, identity_hate)                                                                                             |
| Finalités secondaires             | Journalisation pseudonymisée des appels API à des fins de traçabilité et de conformité RGPD ; détection d'abus et d'utilisation anormale du service                                                                                                                                                                     |
| Base légale                       | **Art. 6.1.f RGPD — Intérêt légitime** à fournir une plateforme de détection et modération de commentaires toxiques. L'intérêt légitime a été mis en balance avec les droits des personnes concernées : l'anonymisation préalable des commentaires réduit l'impact sur la vie privée.                  |
| Traitement automatisé / Profilage | **Oui** — le score est calculé par un modèle ML (DistilBERT) sans intervention humaine. Aucune décision individuelle à effet juridique dans la version actuelle. Une AIPD (Art. 35) serait obligatoire si le score était intégré dans un processus décisionnel (modération automatique, accès, recrutement). |

---

## 3. Données à caractère personnel traitées

### Catégories de personnes concernées (Art. 30.1.c)

- **Utilisateurs de l'API** — développeurs et intégrateurs identifiés par leur clé API (la clé n'est pas journalisée)
- **Auteurs des commentaires analysés** — toute personne dont le commentaire est soumis à analyse 

### Catégories de données traitées (Art. 30.1.c)

| Donnée                     | Nature                                                                                                 | Traitement appliqué                                       | Stockage                                 |
| --------------------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------- | ---------------------------------------- |
| Commentaire brut soumis     | Données à caractère personnel potentielles (contenu personnel, opinions, données sensibles Art. 9) | Anonymisé via spaCy NER + regex avant inférence          | Non — traitement en mémoire uniquement |
| Commentaire prétraité     | Pseudonymisé                                                                                         | Retourné en réponse à l'appelant                        | Non conservé côté serveur             |
| Score de toxicité          | Non DCP (résultat agrégé)                                                                           | Calcul : moyenne des scores des labels dont la probabilité atteint leur seuil, sinon score de `toxic` | Oui — journal applicatif (Cloud Logging)     |
| Longueur du commentaire     | Non DCP (métadonnée)                                                                                 | Nombre de caractères                                      | Oui — journal applicatif (Cloud Logging)     |
| Horodatage UTC              | Non DCP                                                                                                | ISO 8601                                                   | Oui — journal applicatif (Cloud Logging)     |
| Durée d'inférence (ms)    | Non DCP (performance)                                                                                  | Mesure temps réel                                         | Oui — journal applicatif (Cloud Logging)     |

### Données sensibles (Art. 9 & 10 RGPD)

Les commentaires soumis peuvent contenir des données sensibles (opinions politiques, santé, orientation sexuelle, origine ethnique). L'anonymisation préalable réduit ce risque.

**Dataset d'entraînement** : Toxic Comment Classification Challenge (Jigsaw / Google, 2017).

| Caractéristique    | Détail                                                                                                                           |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Source des données | Commentaires des pages de discussion Wikipedia (talk pages), en anglais                                                           |
| Taille              | 159 571 commentaires d'entraînement + 63 978 de test                                                                             |
| Annotation          | Annotation binaire par vote majoritaire d'évaluateurs humains                                                                    |
| Labels              | `toxic`, `severe_toxic`, `obscene`, `threat`, `insult`, `identity_hate` (multi-label)                                 |
| Licence labels      | CC0 (domaine public)                                                                                                              |
| Licence texte       | CC-BY-SA 3.0 (texte Wikipedia)                                                                                                    |
| Biais identifiés   | Corpus exclusivement anglophone, issu de Wikipedia — peut refléter des biais culturels dans la classification `identity_hate` |

---

## 4. Journal de traçabilité

**Où** : sortie standard de l'API, collectée par Cloud Logging (GKE). L'API ne tient ni fichier CSV ni hash de clé (d'après `api/main.py`).
**Principe** : aucun texte brut ni donnée directement identifiante n'est enregistré.

| Champ        | Type             | Description                                                                |
| ------------ | ---------------- | -------------------------------------------------------------------------- |
| horodatage   | datetime UTC     | ajouté par Cloud Logging                                                   |
| `score`      | entier [0–100]   | score de toxicité calculé — résultat agrégé, non ré-identifiable          |
| `longueur`   | entier           | nombre de caractères du texte soumis — aucune information sur le contenu |
| `duree_ms`   | décimal          | durée d'inférence en millisecondes                                         |

Ligne type : `score=87 longueur=142 duree_ms=14.2`

---

## 5. Destinataires et sous-traitants (Art. 30.1.d)

### Destinataires internes

- Équipe technique Digital Social Score (accès aux logs de traçabilité pour monitoring et support)

### Sous-traitants (Art. 28 RGPD)

| Sous-traitant               | Rôle                                       | Localisation des données     | Garanties RGPD                                                            |
| --------------------------- | ------------------------------------------- | ----------------------------- | ------------------------------------------------------------------------- |
| Google Cloud Platform (GKE) | Hébergement Kubernetes, Artifact Registry | UE — europe-west9 (Paris) | Clauses contractuelles types (CCT) — DPA disponible sur cloud.google.com |
| Google Secret Manager       | Stockage sécurisé des clés API           | UE — europe-west9 (Paris) | Certifié ISO 27001, SOC 2 Type II                                        |

### Transferts hors UE (Art. 30.1.e)

**Aucun transfert hors UE.** Le déploiement est restreint à la région `europe-west9` (Paris, France). Aucun traitement n'est réalisé dans des pays tiers sans décision d'adéquation de la Commission européenne.

---

## 6. Durées de conservation (Art. 30.1.f)

| Données                                         | Durée de conservation                                              | Justification                                |
| ------------------------------------------------ | ------------------------------------------------------------------- | -------------------------------------------- |
| Texte brut                                       | **Aucune** — traitement en mémoire uniquement               | Principe de minimisation (Art. 5.1.c)        |
| Texte prétraité                                | **Aucune** côté serveur — retourné en réponse uniquement | Principe de minimisation                     |
| Journal applicatif (Cloud Logging) | **90 jours glissants** — purge automatique                   | Obligation de traçabilité vs. minimisation |
| Poids du modèle DistilBERT                      | Durée du service — révision à chaque nouvelle version           | Nécessité opérationnelle                  |

> **Action requise** : Purger les logs de plus de 90 jours.

---

## 7. Mesures de sécurité techniques et organisationnelles (Art. 32 RGPD)

| Mesure                               | Description technique                                                                                                       | Statut                  |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| Authentification API                 | Clé API via header `X-API-Key`, comparaison à temps constant `secrets.compare_digest` — protection timing attack (`api/main.py`) | Implémentée |
| Chiffrement en transit               | HTTPS forcé via `FrontendConfig` GKE (`redirectToHttps: enabled`) + `ManagedCertificate` Google (`api/k8s/ingress.yaml`) | Implémentée |
| Anonymisation des commentaires       | spaCy NER + regex — 8 balises de remplacement : `personne_tag`, `organisation_tag`, `email_tag`, `url_tag`, `ip_tag`, `telephone_tag`, `pseudo_tag`, `adresse_tag` (`api/preprocessing.py`) | Implémentée |
| Minimisation des logs                | `log.info` sans texte brut : longueur, score, durée uniquement — aucun stockage du contenu (`api/main.py`) | Implémentée |
| Gestion des secrets                  | `secretKeyRef: {name: dss-api-key, key: API_KEY}` dans `api/k8s/deployment.yaml` — clé absente du code source et de l'image Docker | Implémentée |
| Conteneur non-root                   | `useradd --uid 1000 appuser` + `USER 1000` dans `api/Dockerfile` ; `runAsNonRoot: true` + `runAsUser: 1000` dans `api/k8s/deployment.yaml` | Implémentée |
| Réduction des privilèges système     | `allowPrivilegeEscalation: false` + `capabilities: {drop: ["ALL"]}` dans `api/k8s/deployment.yaml` | Implémentée |
| Validation des entrées               | Pydantic `Field(min_length=1, max_length=5000)` — HTTP 422 si dépassement (`api/main.py`) | Implémentée |
| Haute disponibilité                  | `replicas: 2` minimum + `startupProbe` / `readinessProbe` / `livenessProbe` sur `/health` (`api/k8s/deployment.yaml`) | Implémentée |
| Journalisation des accès             | Logs Cloud Logging GKE (rétention 30 jours par défaut) | Par défaut GCP |
| AIPD (Art. 35 RGPD)                  | Analyse d'impact requise si le score est utilisé dans un processus décisionnel à effet juridique | À évaluer selon usage |

---

## 8. Droits des personnes concernées (Art. 12–22 RGPD)

| Droit                    | Article RGPD | Applicable  | Modalités d'exercice                                                                                     |
| ------------------------ | ------------ | ----------- | --------------------------------------------------------------------------------------------------------- |
| Droit d'accès           | Art. 15      | Oui         | Demande par email — les logs pseudonymisés correspondant à la clé sont communicables                  |
| Droit de rectification   | Art. 16      | Limité     | Données pseudonymisées — ré-identification impossible sans la clé d'origine                          |
| Droit à l'effacement    | Art. 17      | Oui         | Purge des logs sur demande — délai max 30 jours                                                         |
| Droit à la limitation   | Art. 18      | Oui         | Suspension de l'enregistrement des logs pour la clé concernée                                           |
| Droit à la portabilité | Art. 20      | Partiel     | Export CSV des logs liés à une clé — format structuré, sur demande                                   |
| Droit d'opposition       | Art. 21      | Oui         | Révocation de la clé API et purge des enregistrements associés                                         |
| Décision automatisée   | Art. 22      | À garantir | Le score DSS ne doit pas être la seule base d'une décision à effet juridique sans intervention humaine |

> **Note** : le journal ne contient pas de hash de clé : les droits d'accès, de portabilité et d'opposition « par clé » ne sont applicables que si ce hash est ajouté au journal.

**Contact pour exercer ses droits** : contact@digitalsocialscore.fr

**Droit de réclamation** (Art. 77 RGPD) :
CNIL — 3 place de Fontenoy, TSA 80715 — 75334 Paris Cedex 07 — www.cnil.fr

---

## 9. Historique des révisions

| Version | Date       | Auteur                       | Modifications      |
| ------- | ---------- | ---------------------------- | ------------------ |
| 1.0     | 12/11/2026 | Équipe Digital Social Score | Création initiale |

---

---

*Document établi en application de l'article 30 du Règlement (UE) 2016/679 (RGPD).*
