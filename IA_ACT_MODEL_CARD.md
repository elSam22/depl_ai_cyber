# Fiche IA Act — Digital Social Score

Membres : NOUDEGBE Situ, OUEDRAOGO Eliana, CAKPOSSA Enzo

Date : 2026-11-16

Version du modèle : DistilBERT 

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

| Critère                                                 | Évaluation                                | Justification                                                                                                                                                                                                                                                            |
| -------------------------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Catégorie de risque**                           | **Risque limité** (Art. 50 IA Act)  | Le système produit un score d'aide à la décision humaine : aucune décision contraignante n'est prise automatiquement sur une personne physique. Le verdict final appartient à un modérateur humain.                                                                |
| **Annex III applicable**                           | Non                                        | Le système ne relève d'aucun des domaines à haut risque listés à l'Annex III : ni éducation, ni emploi, ni services essentiels, ni justice, ni migration, ni infrastructures critiques.                                                                            |
| **Exigence principale**                            | **Transparence** (Art. 50)           | Obligation minimale pour les systèmes à risque limité : les utilisateurs finaux doivent savoir qu'ils interagissent avec un système IA. La documentation de l'API (`/docs`) et la réponse exposent explicitement les limites du modèle (langue, biais, seuils).  |
| **Si déployé en modération à grande échelle** | Risque élevé potentiel (Annex III § 1b) | La surveillance de personnes dans des espaces publics en ligne peut déclencher le régime haut risque. Dans ce cas, les exigences Art. 9-15 s'appliqueraient (gestion des risques, gouvernance des données, documentation technique, supervision humaine, robustesse). |

---

## 3. Données d'entraînement

| Rubrique                    | Détail                                                                                                                                                                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Jeu de données**   | *Toxic Comment Classification Dataset* — Jigsaw.                                                                                                                                                                                              |
| **Origine**           | Commentaires des pages de discussion Wikipédia en anglais.                                                                                                                                                                                      |
| **Volume**            | 159 571 commentaires (train) + 63 978 commentaires labellisés (test).                                                                                                                                                                           |
| **Labels**            | Multi-label, annotés par vote majoritaire d'annotateurs humains.                                                                                                                                                                                |
| **Licences**          | Textes : CC-BY-SA 3.0 (Wikipédia). Labels : CC0 (domaine public).                                                                                                                                                                               |
| **Déséquilibre**    | ≈ 10 % de positifs sur `toxic` ; `threat` et `identity_hate` < 1 %. Corrigé par pondération des classes à l'entraînement.                                                                                                             |
| **Anonymisation**     | Appliquée avant chaque prédiction (et non sur les données d'entraînement originales) : regex sur formats fixes (email, URL, IP, téléphone, pseudo) + NER spaCy (`en_core_web_sm`) pour les noms de personnes et d'organisations.         |
| **Biais identifiés** | Corpus exclusivement anglophone : les performances sur d'autres langues ne sont pas garanties. Biais culturels possibles sur `identity_hate` (terminologie anglophone). Sous-représentation de certains groupes dans les données négatives. |

---

## 4. Performances mesurées

Évaluées sur le test officiel Jigsaw (10 000 lignes communes, graine 42, ~10 % de positifs, lignes `-1` exclues), **seuil optimisé par label** (maximise le F1 sur la validation). Données complètes : `models/resultats.csv` et `DOCUMENTATION.md §2.3`.

| Modèle                | Précision     | Rappel         | F1             | AUC-ROC         |
| ---------------------- | -------------- | -------------- | -------------- | --------------- |
| DistilBERT (déployé) | **0,49** | **0,69** | **0,56** | **0,977** |
| BiLSTM                 | 0,30           | 0,48           | 0,36           | 0,916           |
| LAYA (zéro-shot)      | 0,37           | 0,74           | 0,48           | 0,969           |

> **Note sur l'évaluation de l'évasion (§5.2) :** les tests d'attaque (`attack/evasion.py`) utilisent un échantillon équilibré artificellement (500 toxiques + 500 sains) pour mesurer l'effet de chaque déguisement. Sur cet échantillon, DistilBERT atteint précision = 0,93 / rappel = 0,92 (meilleur que le test réel car il n'y a pas de déséquilibre de classes). Les chiffres du tableau ci-dessus sont les métriques de production réelles.

**Latence (DistilBERT, local Mac M3) :** 14-16 ms (prétraitement + modèle, hors réseau). Sur l'API déployée : ~200 ms.

**Seuils de décision :** calibrés sur la validation pour maximiser le F1 par label (`models/seuils.json`). Les seuils ne sont pas fixes à 0,5 : `threat` et `identity_hate` ont des seuils plus bas pour compenser leur rareté.

---

## 5. Risques identifiés et mesures prises

### 5.1 Risques liés au modèle

| Risque                                           | Niveau               | Justification                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Mesure                                                                                                                      |
| ------------------------------------------------ | -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Faux négatifs** (toxique non détecté) | Élevé              | Rappel mesuré = **0,69** sur le test officiel (~10 % de toxiques, seuil optimisé) : environ **31 % des commentaires toxiques ne sont pas détectés** en conditions réelles. Sur l'échantillon d'attaque équilibré (50/50), le rappel monte à 0,92 — mais ce n'est pas la distribution réelle. Sous évasion active (leetspeak, lettres espacées), le rappel chute à **0,40** : un toxique sur deux passe. L'impact est direct : les personnes ciblées par du harcèlement ne sont plus protégées. | Rappel communiqué dans la réponse API ; aucune décision finale automatique sans validation humaine recommandée.         |
| **Faux positifs** (sain signalé toxique)  | Moyen                | Précision mesurée = **0,49** sur le test officiel (seuil optimisé) : environ **51 % des alertes portent sur des textes sains**. Ce chiffre élevé s'explique par le déséquilibre des classes (~10 % de toxiques) et les seuils calibrés pour maximiser le rappel. L'impact reste modéré car aucune décision contraignante n'est automatique : le verdict final est humain. Sur l'échantillon équilibré d'attaque, la précision est de 0,93 (absence de déséquilibre).                                  | Précision et probabilités par label exposées dans la réponse ; seuils ajustables par label dans `models/seuils.json`. |
| **Biais sur certains groupes**             | Moyen                | Le corpus Jigsaw est exclusivement anglophone et reflète des biais culturels anglophones, notamment sur le label `identity_hate` (terminologie, références). Les groupes vulnérables sous-représentés dans les données négatives peuvent être sur-signalés. Le niveau "Moyen" reflète que les biais sont **connus et documentés**, mais non corrigés à la source (rééquilibrage uniquement par pondération des classes).                                                                                  | Jeu de données publiquement audité (Jigsaw / Google) ; biais détaillés au §3.                                          |
| **Corpus anglophone uniquement**           | Élevé hors anglais | Le modèle a été entraîné et évalué uniquement sur des commentaires Wikipédia en anglais. Sur d'autres langues, les performances ne sont **ni mesurées ni garanties** : le risque de faux négatifs incontrôlé est élevé. L'usage hors anglais crée une fausse impression de sécurité.                                                                                                                                                                                                                        | Usage documenté comme strictement limité à l'anglais dans la réponse API et la documentation.                           |

### 5.2 Risques de sécurité

| Attaque testée                                                                        | Impact mesuré                                            | Défense déployée                                                                                                                                   | Impact après défense                                               |
| -------------------------------------------------------------------------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| **Évasion** (leetspeak, homoglyphes, caractères invisibles, lettres espacées) | Rappel 0,92 → 0,40 (évasion jusqu'à 57 %)              | `normaliser_anti_evasion()` dans `api/preprocess.py` : NFKC, suppression invisibles, homoglyphes → latin, regroupement espaces, dé-leet prudent | Rappel 0,81–0,93 ; évasion 0–12 %                                 |
| **Noyage** (texte toxique noyé dans ≥ 1 000 chars neutres)                     | Proba toxic 0,99 → 0,096 (évasion 100 %)                | Scan en fenêtres glissantes de 128 tokens dans `api/modeles.py`                                                                                    | Proba toxic ~0,93 ; évasion 0 %                                     |
| **Vol de modèle** (rafale de requêtes pour cloner le modèle)                  | 1 442 req exploitables en 20 s, accord clone/cible 94,7 % | Limiteur de débit glissant (`api/limiteur_debit.py`) : 60 req/60 s par IP, rejet HTTP 429                                                          | 60 req exploitables en 20 s (×24), ~33 min pour atteindre 2 000 req |

### 5.3 Risques résiduels

| Risque résiduel                                             | Statut                                                                                                                                                         |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Évasion leetspeak partielle (12 %)                          | Dé-leet prudent par conception pour éviter de casser les nombres ("3pm", "v2"). Acceptable.                                                                  |
| Clonage possible par un attaquant patient (plusieurs heures) | Le limiteur ralentit sans rendre impossible. Complément possible : monitoring des anomalies de débit.                                                        |
| Attaques par synonymes / mutation                            | **Non mesurées sur notre modèle** (voir `attack/test_synonymes_mutation.py`, résultats non sauvegardés). Sur les modèles des autres équipes : 1/15 évasion (Florentin & Gilane) et 9/15 (Exauce & Gilbert, modèle sur mots-clés). DistilBERT résiste théoriquement mieux grâce aux sous-mots et au contexte, mais aucune mesure propre n'est disponible. À tester. |

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
| **Minimisation de l'information exposée** | Réponse limitée au nécessaire ; logs sans texte (RGPD). **Faiblesse non corrigée : `/docs` est public** (FastAPI expose la documentation de l'API sans authentification). Risque résiduel documenté dans `DOCUMENTATION.md §3.2`. |
| **Reproductibilité**                      | Seuils exportés (`models/seuils.json`), version du modèle exposée dans `/health` et chaque réponse, graine d'entraînement fixée. |

---

## 8. Limitations connues et usage déconseillé

- **Ne pas utiliser** comme seul outil de décision de modération : un modèle à 69 % de rappel (test officiel, seuil optimisé) laisse passer ~31 % des commentaires toxiques en conditions réelles.
- **Ne pas utiliser** sur des textes dans une langue autre que l'anglais sans réévaluation des performances.
- **Ne pas utiliser** pour des décisions ayant un impact juridique ou réglementaire sur des personnes physiques sans audit indépendant.
- Le score 0-100 est une probabilité calibrée, pas un verdict absolu : un score de 45 est proche du seuil et doit être traité avec prudence.

---

## 9. Gouvernance et responsabilité

#### Responsable du traitement IA

| Champ                   | Valeur                                                           |
| ----------------------- | ---------------------------------------------------------------- |
| **Dénomination** | Équipe Digital Social Score                                     |
| **Projet**        | Digital Social Score API — analyse de toxicité de commentaires |
| **Membres**       | NOUDEGBE Situ, OUEDRAOGO Eliana, CAKPOSSA Enzo                   |
| **Localisation**  | France                                                           |
| **Contact**       | contact@digitalsocialscore.fr                                    |

#### Cycle de vie du système

| Champ                          | Valeur                                                                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Version courante**     | 1.0 (DistilBERT fine-tuné, novembre 2026)                                                                                           |
| **Révision des seuils** | À recalibrer si la distribution des données d'entrée change (nouvelle langue, nouveau type de plateforme, dérive de population). |
| **Audit de sécurité**  | Dernière évaluation : 2026-11-16 (TP2). À renouveler à chaque évolution majeure du modèle ou de l'API.                         |
| **Retrait du système**  | Décision des responsables ; les données d'entraînement et les modèles sont supprimés à la mise hors service.                   |
