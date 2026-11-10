# Anonymisation des commentaires — approche regex + NER spaCy

Notebook : [anonyme_2.ipynb](notebooks/anonyme_2.ipynb) · Entrées : `data/train.csv`, `data/test.csv` · Sorties : `data/anonymise/train_anonyme_2.csv`, `data/anonymise/test_anonyme_2.csv`

Données : commentaires du *Toxic Comment Classification Dataset* (colonne `comment_text`, commentaires de pages de discussion Wikipédia). Seule `comment_text` est modifiée ; `id` et les colonnes de toxicité sont conservées.

---

## 1. Méthode

Pour chaque commentaire :

1. **Regex** : détection des informations à format fixe (email, téléphone FR/international, URL, IPv4/IPv6, `@pseudo`, `User:Pseudo`, `User talk:Pseudo`, **adresses précises** : rue + numéro, code postal).
2. **NER spaCy** (`en_core_web_sm`) : détection des **personnes** (`PERSON`) et des **organisations** (`ORG`). Les lieux (`GPE`, `LOC` : villes, pays, continents) et les groupes (`NORP`) ne sont **pas** masqués.
3. **Fusion** des deux listes de positions en un seul passage sur le texte original (le regex est prioritaire, aucun chevauchement).
4. **Remplacement** de chaque morceau par une étiquette : `personne_tag`, `organisation_tag`, `email_tag`, `url_tag`, `ip_tag`, `telephone_tag`, `pseudo_tag`, `adresse_tag`. Ces balises sont définies à un seul endroit du notebook (le dict `BALISES`). Il n'y a pas de balise pour les lieux.

## 2. Comparaison version initiale / version anonymisée

### 2.1 Exemples

| Avant | Après |
|---|---|
| `Your vandalism to the Matt Shirvington article has been reverted.` | `Your vandalism to the personne_tag article has been reverted.` |
| `…anything you want to add. 67.101.255.166` | `…anything you want to add. ip_tag` |
| `I suggest User:FisherQueen, the "girl" who protected him.` | `I suggest User:pseudo_tag, the "girl" who protected him.` |
| `I live at 12 rue de la Paix, 75002 Paris, in France.` | `I live at adresse_tag, in France.` *(la ville et le pays isolés sont conservés)* |
| `…retired now.89.205.38.27` | `…retired now.89.205.38.27` *(IP non masquée : voir 2.3)* |

### 2.2 Chiffres (fichiers complets)

> **Run précédent (v1)** : ces chiffres datent d'une version où les lieux étaient masqués (`[LIEU]`) et où `[ADRESSE]` n'existait pas. Les fichiers `*_anonyme_2.csv` ont depuis été regénérés avec la méthode actuelle, mais **ce tableau n'a pas encore été mis à jour** avec les nouveaux comptages (à recopier depuis le bilan du notebook).

| | `train` | `test` |
|---|---|---|
| Lignes | 159 571 | 153 164 |
| Commentaires modifiés | 65,0 % | 60,5 % |
| `[PERSONNE]` | 117 812 | 122 084 |
| `[ORGANISATION]` | 166 266 | 142 258 |
| `[LIEU]` | 69 027 | 61 477 |
| `[IP]` | 9 789 | 4 666 |
| `[URL]` | 8 032 | 6 410 |
| `[PSEUDO]` | 5 105 | 1 297 |
| `[EMAIL]` | 467 | 537 |
| `[TELEPHONE]` | 79 | 98 |
| **Total entités** | **376 577** | **338 827** |

La longueur moyenne d'un commentaire reste stable (≈ 394 caractères avant et après sur `train`) : les étiquettes remplacent des morceaux de taille comparable.

### 2.3 Limites constatées (aucun jeu annoté : pas de précision/rappel chiffrés)

Ces constats viennent de la lecture des sorties, pas d'une évaluation sur vérité terrain.

1. **Faux positifs du NER.** (constaté sur la v1) `Wikipedia` est très souvent masqué comme organisation (≈ 1 800 fois dans les 6 000 premiers commentaires modifiés de `train`). Des sigles du jargon Wikipédia sont masqués à tort : `UTC`, `POV`, `NPOV`, `BLP`, `LOL`. `Wiki` est pris pour une personne ; `New York Dolls FAC` était découpé en `[LIEU] [ORGANISATION]`. `en_core_web_sm` est un petit modèle, peu adapté à ce texte informel.
2. **IP non détectées quand elles suivent directement un point** (`now.89.205.38.27`) : le motif exclut les IP précédées d'un point. Il reste environ **1 100 IPv4 valides** dans `train_anonyme_2.csv` et 12 dans `test_anonyme_2.csv`.
3. **`::` seul masqué comme IPv6**, alors que ce n'est pas une adresse utile.
4. **Pseudos sans préfixe non détectés** (`Hardcore Metallica Fan`, `Sityush`) : le regex ne cible que `User:` et `@`.
5. **Pseudos mal découpés** : la virgule finale est parfois incluse (`Physicq210,`), et un mot courant (`The`) a été pris pour un pseudo.
6. **Personnalités publiques masquées** (`Hitler`, `Bush`, `Jesus`) : ce n'est pas une donnée personnelle au sens strict, c'est un effet du NER.

### 2.4 Corrections apportées (v3)

Après analyse des fichiers anonymisés, les filtres suivants ont été ajoutés dans `notebooks/anonyme_2.ipynb`. Chiffres mesurés avant relance complète : regex sur tout `train.csv`, NER sur un échantillon de 20 000 lignes.

| Problème constaté | Correction | Effet mesuré |
|---|---|---|
| Insultes masquées comme personnes (`moron` ×202, `dick faggot`, `faggot!!!!…`) | Toute entité contenant un mot de la liste `MOTS_TOXIQUES` ou une racine toxique (`fuck`, `shit`, `nigg`…) n'est plus masquée. | 0 entité masquée contenant un mot toxique (échantillon). |
| Jargon Wikipédia pris pour des organisations (`Wikipedia` ≈ 19 % des ORG, `UTC`, `POV`, `BLP`, `Wikipedia:Questions`) | Liste `JARGON_WIKI` + tout mot commençant par `wiki`, pour les ORG et les PERSON d'un seul mot de jargon (`Wiki`). | Plus aucun `Wikipedia`/`UTC`/`POV` dans les ORG masquées. |
| Personnalités publiques masquées (`Mitt Romney`, `Hitler`, `Jesus`, `pro-Assad`) | Liste `PERSONNALITES_PUBLIQUES` : ce ne sont pas des données personnelles de commentateurs. | Plus masquées. |
| Mots courants masqués (`hi` ×189, `admin`, `cheers`, `fyi`, `ffffff`) | Liste `MOTS_COURANTS`, règle « un seul mot tout en minuscules = erreur du NER », règle code couleur hexadécimal. | Plus masqués. |
| IP non masquées après un point (`now.89.205.38.27`, ≈ 1 100) | Motif IPv4 corrigé (seules les suites plus longues type `1.2.3.4.5` sont exclues). | 26 IPv4 valides non masquées sur 11 232 dans `train` (collées à d'autres chiffres). |
| Nom collé à une insulte resté en clair (`Stupid Bob Smith`) | Les mots toxiques sont retirés de l'entité et seul le reste est masqué, s'il ressemble à un nom (majuscule initiale) : `Stupid Fucking personne_tag`. Un texte crié (`DIE FAG DIE`) reste intact. | Comparaison avant/après sur 20 000 lignes : aucune insulte masquée par le NER. |
| `::` seul masqué comme IPv6 ; ponctuation finale incluse dans les pseudos (`User:Physicq210,`) | IPv6 : au moins un chiffre hexadécimal exigé. Pseudos : ponctuation finale retirée du masque. | `::` conservé ; `User:pseudo_tag,`. |
| Faux positifs d'adresse (`2008 The Way`, `20006 Annual`, `2012 MTC Drive`, `N00BS`, `D0D4FF`) | Types de voie ambigus retirés (`Way`, `Place`, `Court`, `Dr`), années 1900-2035 exclues, mots de campagne Wikipédia exclus, code postal français seul abandonné, État US valide obligatoire, espace obligatoire dans le code postal UK. | 104 adresses dans `train`, quasiment toutes de vraies adresses (`1600 Pennsylvania Avenue`, `CA 94709`, `E1 4AA`). |

Résultat sur l'échantillon : 1,45 balise par commentaire (contre 1,93) et 51 % des commentaires avec au moins une balise (contre 61 %). Les vrais prénoms et noms (`John`, `Jessica Simpson`) et les vraies organisations (`Google`, `BBC`, `CIA`) restent masqués.

**Limites restantes :** le NER `en_core_web_sm` laisse encore quelques faux positifs isolés en ORG (`time`, `never`, `template`, `introduction`). Les listes de filtrage sont faites à la main à partir des valeurs les plus fréquentes : elles ne couvrent pas tout. Les pseudos sans préfixe `User:` ou `@` ne sont toujours pas détectés.

**Conséquence :** le résultat réduit fortement la présence de données personnelles mais **ne garantit pas une anonymisation complète**. Il doit être considéré comme une **pseudonymisation / minimisation** tant qu'un contrôle sur jeu annoté n'a pas été fait.

## 3. Justification de chaque choix

| Choix | Pourquoi | Limite |
|---|---|---|
| Regex pour email, URL, IP, téléphone, pseudo, adresse | Formats fixes : détection fiable, déterministe et très rapide. | Ne trouve que ce qui respecte un format (cf. 2.3 points 2 et 4). |
| NER spaCy pour personnes, lieux, organisations | Les noms propres n'ont pas de format fixe ; il faut un modèle qui exploite le contexte. | Faux positifs sur le jargon et les majuscules (cf. 2.3 point 1). |
| `en_core_web_sm` | Léger, rapide (≈ 3 ms/commentaire), suffisant pour traiter ≈ 310 000 lignes en ≈ 20 min sur un poste standard. | Moins précis que les modèles plus gros (`md`, `lg`, `trf`). |
| Entités NER retenues : PERSON et ORG uniquement | Ce sont celles qui identifient directement une personne ou son employeur/groupe. | Les ORG sont la source principale de faux positifs. |
| Villes, pays et continents (`GPE`, `LOC`) **non masqués** | Non identifiants seuls et utiles à la détection (un propos haineux peut viser un pays ou une région). Les masquer retirerait du signal. Ils étaient aussi une source de faux positifs (`POV`, `US`, `NPOV`…). | Risque résiduel faible : combinés à d'autres informations, ils peuvent aider à ré-identifier quelqu'un. |
| Adresses précises → `[ADRESSE]` (rue + numéro, code postal FR/UK/US) | Une adresse précise identifie un foyer, contrairement à une ville. Motifs prudents : numéro + type de voie non ambigu, nom de rue en majuscule initiale, années exclues ; code postal UK avec espace, code postal US avec un sigle d'État valide (cf. 2.4). | Formats anglo-saxon et français seulement ; un code postal français seul n'est pas masqué (trop de faux positifs). |
| ORG de moins de 3 caractères ignorées | Évite le bruit (« FA », « UN »…). | Peut laisser passer une vraie organisation très courte. |
| `NORP` non masqué, mots toxiques non masqués | Les groupes ne sont pas identifiants ; les mots toxiques sont justement le signal à classer. Les mots toxiques sont retirés des entités NER avant masquage. | Un groupe très petit pourrait être identifiant (cas marginal). Une insulte absente de la liste ou déformée (`m0ron`) peut encore être prise pour un nom. |
| Jargon Wikipédia, personnalités publiques et mots courants non masqués | Ce ne sont pas des données personnelles ; les masquer ajoutait du bruit (cf. 2.4). | Listes faites à la main, non exhaustives. |
| Regex prioritaire sur le NER | Plus précis sur les formats fixes (ex. un email contenant un nom). | — |
| Un seul passage sur le texte original | Évite les décalages de positions entre deux remplacements successifs. | — |
| Balises typées (`xxx_tag`) plutôt que suppression | Conserve la structure de la phrase et le type d'information pour la classification de toxicité. | Révèle qu'une entité existait à cet endroit. |
| Pour `User:Pseudo`, seul le pseudo est masqué | Le préfixe n'est pas une donnée personnelle et reste utile au contexte. | — |
| Validation des IP avec `ipaddress` ; téléphone entre 9 et 15 chiffres | Évite de masquer des heures (`21:51`), de faux `999.1.1.1` ou des suites de chiffres quelconques. | Quelques faux positifs/négatifs restent possibles. |
| Pas de jeu annoté à la main | Décision du groupe (pas d'annotations disponibles). | Pas de précision/rappel chiffrés (cf. 2.3). |

---

## 4. Registre de traitement des données

Format inspiré de l'article 30 du RGPD. Les champs marqués **[À compléter]** dépendent du cadre réel du projet et doivent être confirmés par le responsable du projet ; ils n'ont pas été inventés ici.

| Rubrique | Contenu |
|---|---|
| **Nom du traitement** | Anonymisation de commentaires (regex + NER spaCy). |
| **Responsable du traitement** | [À compléter : établissement / enseignant / groupe projet] |
| **Contact (DPO ou référent)** | [À compléter] |
| **Finalité** | Réduire la présence de données personnelles dans les commentaires avant utilisation pour un projet de classification de toxicité (cadre pédagogique). |
| **Base légale** | [À compléter / valider : ex. mission d'enseignement ou intérêt légitime. Non déterminée ici.] |
| **Personnes concernées** | Auteurs de commentaires de pages de discussion Wikipédia et personnes mentionnées dans ces commentaires. |
| **Catégories de données traitées** | Texte libre (`comment_text`) pouvant contenir : noms de personnes, pseudonymes, adresses IP, emails, numéros de téléphone, URL, adresses postales, organisations, lieux. Les libellés de toxicité (`toxic`, `insult`, `identity_hate`…) peuvent révéler des opinions ou des attaques visant des groupes : **données potentiellement sensibles**. |
| **Source des données** | *Toxic Comment Classification Dataset* (fichiers `train.csv`, `test.csv`, fournis pour le cours). Origine à citer : [À compléter : lien/licence exacts]. |
| **Volume** | 159 571 commentaires (train) et 153 164 (test). |
| **Villes, pays, continents conservés** | Non identifiants seuls, utiles à la détection ; risque résiduel faible. |
| **Opérations réalisées** | Lecture des CSV → détection par regex et NER → remplacement par étiquettes → écriture de nouveaux CSV. Aucun envoi vers un service externe : le traitement est local. |
| **Outils** | Python 3.12, spaCy 3.8 (`en_core_web_sm`), pandas, `ipaddress`, `tqdm` — dans un environnement virtuel local (`.venv`). |
| **Destinataires** | Membres du groupe projet et enseignant via le dépôt GitHub. **Le dépôt est public** : toute publication des fichiers bruts ou anonymisés y est visible de tous. |
| **Transferts hors UE** | Hébergement GitHub (États-Unis) du dépôt : [À compléter / valider]. Le traitement lui-même n'envoie rien à un tiers. |
| **Fichiers produits** | `data/anonymise/train_anonyme_2.csv`, `data/anonymise/test_anonyme_2.csv` (versions modifiées) ; les fichiers d'origine restent inchangés. |
| **Durée de conservation** | [À compléter : ex. durée du module]. Les fichiers bruts ne devraient pas rester dans le dépôt public au-delà du nécessaire. |
| **Mesures de sécurité / minimisation** | Remplacement des identifiants directs par des étiquettes ; traitement local ; fichiers d'origine non modifiés ; environnement virtuel isolé. |
| **Risques résiduels** | Anonymisation incomplète (cf. 2.3) : IP restantes, pseudos sans préfixe, noms mal reconnus. Un auteur reste potentiellement ré-identifiable par recoupement avec Wikipédia (le texte original y est public). |
| **Recommandations** | 1) Corriger les IP précédées d'un point. 2) Filtrer le jargon (`Wikipedia`, `UTC`, `POV`…). 3) Relancer le notebook (méthode mise à jour : sans `[LIEU]`, avec `[ADRESSE]`) pour regénérer les CSV et le tableau 2.2. 4) Évaluer sur un jeu annoté. 5) Ne pas publier les fichiers bruts dans un dépôt public. |

## 5. Étape 2 : nettoyage des textes

Notebook [clean_text.ipynb](notebooks/clean_text.ipynb) (fonction `clean_text` + application), sur `data/anonymise/*_anonyme_2.csv` → `data/clean/train_clean.csv`, `data/clean/test_clean.csv` :

1. minuscules ;
2. suppression des emojis (plages Unicode) ;
3. suppression de la ponctuation avec `re.sub(r"[^\w\s]", " ", text)` : le `_` est conservé, donc les balises `*_tag` restent intactes ;
4. espaces multiples et retours à la ligne ramenés à un seul espace.

Le notebook affiche 5 exemples avant/après et vérifie, ligne par ligne, que chaque balise apparaît le même nombre de fois avant et après. **Prérequis :** les CSV anonymisés doivent avoir été générés avec les nouvelles balises `*_tag` (relancer d'abord l'anonymisation).

## 6. Étape 2 : Entraînement des modèles

Notebook [train.ipynb](notebooks/train.ipynb) · Données : `data/clean/train_clean.csv` · Split : 80 % entraînement / 20 % validation (graine 42) · Test officiel : `data/clean/test_clean.csv` + `data/test_labels.csv` (lignes à `-1` retirées).

Trois modèles comparés, même seuil de décision (0,5), même split, même métrique (macro sur les 6 labels).

### Tableau récapitulatif — validation (20 % de train)

| Modèle | Entraînement (s) | Précision | Rappel | F1 | ROC-AUC | ms/commentaire |
|---|---|---|---|---|---|---|
| BiLSTM | 88 | 0.278 | 0.940 | 0.391 | 0.977 | 0.08 |
| DistilBERT | 1 710 | 0.321 | 0.955 | 0.439 | 0.985 | 9.08 |
| LAYA (zéro-shot) | 0 | 0.366 | 0.881 | 0.431 | 0.966 | 417 |

### Tableau récapitulatif — test officiel Kaggle (sans lignes à -1)

| Modèle | Précision | Rappel | F1 | ROC-AUC | ms/commentaire | Lignes évaluées |
|---|---|---|---|---|---|---|
| BiLSTM | 0.169 | 0.948 | 0.267 | 0.965 | 0.08 | 63 978 |
| DistilBERT | 0.199 | 0.967 | 0.309 | 0.978 | 8.34 | 63 978 |
| LAYA (zéro-shot) | 0.244 | 0.900 | 0.333 | 0.971 | 417 | 2 000 |

### Analyse

- **BiLSTM** : le plus rapide à l'inférence (0,08 ms/commentaire), entraîné en 88 s. Rappel très élevé (0,94) mais précision faible (0,28) : il sur-détecte la toxicité.
- **DistilBERT** : meilleur F1 (0,44) et meilleur ROC-AUC (0,985) sur la validation. 28× plus lent que BiLSTM à l'inférence, entraînement ~30 min. Meilleur choix qualité/déploiement.
- **LAYA (zéro-shot)** : meilleure précision parmi les trois (0,37) mais inférence très lente (417 ms/commentaire). Utilisable uniquement en mode asynchrone, non adapté à une API temps réel.

### Choix pour le déploiement (Étape 3)

**DistilBERT** est retenu pour l'API : meilleur compromis précision/rappel, inférence acceptable (< 10 ms), modèle sauvegardé dans `models/distilbert/`.

---

## 7. Reproduire

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # inclut le modèle spaCy en_core_web_sm
# ouvrir notebooks/anonyme_2.ipynb avec le kernel .venv puis exécuter toutes les cellules (~20 min)
```
