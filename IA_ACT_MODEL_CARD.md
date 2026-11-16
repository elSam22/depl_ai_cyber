#   Fiche IA Act — Digital Social Score

Membres : NOUDEGBE Situ, OUEDRAOGO Eliana, CAKPOSSA Enzo

Date : 2026-11-16

Version du modèle : DistilBERT fine-tuné (voir models/distilbert/)

---

## 1. Description du système

| Rubrique                 | Détail                                                                                                                                                                                        |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Nom**            | Digital Social Score (DSS)                                                                                                                                                                     |
| **Finalité**      | Attribuer un score de toxicité (0 à 100) à un commentaire textuel en ligne, pour aider à la modération de contenu.                                                                        |
| **Type de tâche** | Classification multi-label supervisée (6 labels : `toxic`, `severe_toxic`, `obscene`, `threat`, `insult`, `identity_hate`).                                                       |
| **Entrée**        | Texte libre en anglais (1 à 5 000 caractères).                                                                                                                                               |
| **Sortie**         | Score global 0-100, verdict booléen `toxique`, probabilités par label, liste des labels détectés.                                                                                        |
| **Architecture**   | DistilBERT (`distilbert-base-uncased`) fine-tuné avec une tête de classification multi-label (6 sorties sigmoïde). Deux modèles alternatifs : BiLSTM (plus léger) et LAYA (zéro-shot). |
| **Déploiement**   | API REST (FastAPI) exposée via Kubernetes sur Google Cloud. Authentification par clé API (`X-API-Key`).                                                                                    |

---

## 2. Classification IA Act

| Critère                                                 | Évaluation                                                                                                                                                                                 |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Catégorie de risque**                           | **Risque limité** (Art. 50 IA Act) — le système ne prend pas de décision contraignante sur une personne physique ; il produit un score d'aide à la décision humaine.            |
| **Annex III applicable**                           | Non : le système n'est pas utilisé dans les domaines listés (éducation, emploi, services essentiels, justice, migration, infrastructures critiques).                                    |
| **Exigence principale**                            | **Transparence** (Art. 50) : les utilisateurs finaux doivent être informés qu'ils interagissent avec un système IA, et les opérateurs doivent documenter les limites du système. |
| **Si déployé en modération à grande échelle** | Risque élevé potentiel (Annex III § 1b) : surveillance des personnes dans les espaces publics en ligne. Dans ce cas, les exigences Art. 9-15 s'appliquent.                               |

---

## 3. Données d'entraînement

| Rubrique                    | Détail                                                                                                                                                                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Jeu de données**   | *Toxic Comment Classification Dataset* — Jigsaw / Google, 2017.                                                                                                                                                                               |
| **Origine**           | Commentaires des pages de discussion Wikipédia en anglais.                                                                                                                                                                                      |
| **Volume**            | 159 571 commentaires (train) + 63 978 commentaires labellisés (test).                                                                                                                                                                           |
| **Labels**            | Multi-label, annotés par vote majoritaire d'annotateurs humains.                                                                                                                                                                                |
| **Licences**          | Textes : CC-BY-SA 3.0 (Wikipédia). Labels : CC0 (domaine public).                                                                                                                                                                               |
| **Déséquilibre**    | ≈ 10 % de positifs sur `toxic` ; `threat` et `identity_hate` < 1 %. Corrigé par pondération des classes à l'entraînement.                                                                                                             |
| **Anonymisation**     | Appliquée avant chaque prédiction (et non sur les données d'entraînement originales) : regex sur formats fixes (email, URL, IP, téléphone, pseudo) + NER spaCy (`en_core_web_sm`) pour les noms de personnes et d'organisations.         |
| **Biais identifiés** | Corpus exclusivement anglophone : les performances sur d'autres langues ne sont pas garanties. Biais culturels possibles sur `identity_hate` (terminologie anglophone). Sous-représentation de certains groupes dans les données négatives. |

---

## 4. Performances mesurées

Évaluées sur le test officiel Jigsaw (labels publics, graine 42, 500 toxiques + 500 sains, voir `attack/evasion.py`).

| Modèle                | Précision | Rappel         | F1    | AUC-ROC     |
| ---------------------- | ---------- | -------------- | ----- | ----------- |
| DistilBERT (déployé) | 0,93       | **0,92** | 0,93  | ~0,97       |
| BiLSTM                 | ~0,89      | ~0,85          | ~0,87 | ~0,93       |
| LAYA (zéro-shot)      | ~0,80      | ~0,75          | ~0,77 | non mesuré |

**Latence (DistilBERT, local Mac M3) :** 14-16 ms (prétraitement + modèle, hors réseau). Sur l'API déployée : ~200 ms (TP1 §5).

**Seuils de décision :** calibrés sur la validation pour maximiser le F1 par label (`models/seuils.json`). Les seuils ne sont pas fixes à 0,5 : `threat` et `identity_hate` ont des seuils plus bas pour compenser leur rareté.

---

## 5. Risques identifiés et mesures prises

### 5.1 Risques liés au modèle

| Risque                                           | Niveau               | Mesure                                                                                                           |
| ------------------------------------------------ | -------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **Faux négatifs** (toxique non détecté) | Élevé              | Rappel mesuré (0,92) et communiqué ; aucune décision automatique finale sans validation humaine recommandée. |
| **Faux positifs** (sain signalé toxique)  | Moyen                | Précision mesurée (0,93) ; probabilités par label exposées pour permettre une revue humaine.                 |
| **Biais sur certains groupes**             | Moyen                | Jeu de données publiquement audité (Jigsaw) ; biais documentés dans §3.                                      |
| **Corpus anglophone uniquement**           | Élevé hors anglais | Usage documenté comme limité à l'anglais ; comportement sur d'autres langues non garanti.                     |

### 5.2 Risques de sécurité (TP2 — étape 2 et 3)

| Attaque testée                                                                        | Impact mesuré                                          | Défense déployée                                                                                                                                   | Impact après défense                                               |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| **Évasion** (leetspeak, homoglyphes, caractères invisibles, lettres espacées) | Rappel 0,92 → 0,40 (évasion jusqu'à 57 %)            | `normaliser_anti_evasion()` dans `api/preprocess.py` : NFKC, suppression invisibles, homoglyphes → latin, regroupement espaces, dé-leet prudent | Rappel 0,81–0,93 ; évasion 0–12 %                                 |
| **Noyage** (texte toxique noyé dans ≥ 1 000 chars neutres)                     | Proba toxic 0,99 → 0,096 (évasion 100 %)              | Scan en fenêtres glissantes de 128 tokens dans `api/modeles.py`                                                                                    | Proba toxic ~0,93 ; évasion 0 %                                     |
| **Vol de modèle** (rafale de requêtes pour cloner le modèle)                  | 1 442 req exploitables en 20 s, accord clone/cible 94 % | Limiteur de débit glissant (`api/limiteur_debit.py`) : 60 req/60 s par IP, rejet HTTP 429                                                          | 60 req exploitables en 20 s (×24), ~33 min pour atteindre 2 000 req |

### 5.3 Risques résiduels

| Risque résiduel                                             | Statut                                                                                                  |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Évasion leetspeak partielle (12 %)                          | Dé-leet prudent par conception pour éviter de casser les nombres ("3pm", "v2"). Acceptable.           |
| Clonage possible par un attaquant patient (plusieurs heures) | Le limiteur ralentit sans rendre impossible. Complément possible : monitoring des anomalies de débit. |
| Attaques par synonymes / mutation                           | Testées directement sur notre modèle : 0 % d'évasion. DistilBERT comprend le sens par sous-mots et contexte — aucune défense supplémentaire nécessaire. |

---

## 6. Transparence et droits des utilisateurs (Art. 13 et 50)

| Exigence                                  | Mise en œuvre                                                                                                     |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| **Information sur l'usage de l'IA** | La documentation de l'API (`/docs`) indique explicitement qu'un modèle IA est utilisé et donne ses limites.    |
| **Score interprétable**            | La réponse expose les probabilités par label et le seuil utilisé pour chacun, pas seulement le verdict final.   |
| **Logs sans données personnelles** | Le texte soumis n'est jamais enregistré ni stocké (RGPD). Seuls la longueur, le score et la durée sont loggés. |
| **Clé API requise**                | L'accès est contrôlé ; aucune requête anonyme n'est acceptée en production.                                   |
| **Documentation**                   | `DOCUMENTATION.md` décrit la chaîne complète, les choix de conception, les limites et les biais identifiés.  |

---

## 7. Robustesse et cybersécurité (Art. 15)

> Art. 15 §1 : *"Les systèmes d'IA à haut risque sont conçus et développés de façon à atteindre un niveau approprié d'exactitude, de robustesse et de cybersécurité, et à fonctionner de manière cohérente à cet égard tout au long de leur cycle de vie."*

| Exigence Art. 15                                 | Mesure                                                                                                                                     |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **Résistance aux exemples adverses**      | Défense anti-évasion et anti-noyage déployées et testées avant/après (§5.2).                                                        |
| **Résistance aux abus d'accès**          | Limiteur de débit, authentification par clé API, validation de l'entrée (longueur max, champ obligatoire).                              |
| **Continuité de service**                 | Liveness probe Kubernetes (`/health`), redémarrage automatique, Prometheus + alertes.                                                   |
| **Minimisation de l'information exposée** | Réponse limitée au nécessaire ; logs sans texte (RGPD) ; documentation masquée en production (`ENV=prod`).                           |
| **Reproductibilité**                      | Seuils exportés (`models/seuils.json`), version du modèle exposée dans `/health` et chaque réponse, graine d'entraînement fixée. |

---

## 8. Limitations connues et usage déconseillé

- **Ne pas utiliser** comme seul outil de décision de modération : un modèle à 92 % de rappel laisse passer ~8 % des commentaires toxiques.
- **Ne pas utiliser** sur des textes dans une langue autre que l'anglais sans réévaluation des performances.
- **Ne pas utiliser** pour des décisions ayant un impact juridique ou réglementaire sur des personnes physiques sans audit indépendant.
- Le score 0-100 est une probabilité calibrée, pas un verdict absolu : un score de 45 est proche du seuil et doit être traité avec prudence.

---

## 9. Gouvernance et responsabilité

#### Responsable du traitement IA

| Champ | Valeur |
|---|---|
| **Dénomination** | Équipe Digital Social Score |
| **Projet** | Digital Social Score API — analyse de toxicité de commentaires |
| **Membres** | NOUDEGBE Situ, OUEDRAOGO Eliana, CAKPOSSA Enzo |
| **Localisation** | France |
| **Contact** | contact@digitalsocialscore.fr |

#### Cycle de vie du système

| Champ | Valeur |
|---|---|
| **Version courante** | 1.0 (DistilBERT fine-tuné, novembre 2026) |
| **Révision des seuils** | À recalibrer si la distribution des données d'entrée change (nouvelle langue, nouveau type de plateforme, dérive de population). |
| **Audit de sécurité** | Dernière évaluation : 2026-11-16 (TP2). À renouveler à chaque évolution majeure du modèle ou de l'API. |
| **Retrait du système** | Décision des responsables ; les données d'entraînement et les modèles sont supprimés à la mise hors service. |
