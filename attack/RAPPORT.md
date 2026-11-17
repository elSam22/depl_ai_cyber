# TP2 : attaque par évasion sur le modèle Digital Social Score

Script : [evasion.py](evasion.py). Résultats : [results/](results/).

## 1. Fiche d'analyse « Attaque IA » (étape 1)

| Rubrique | Contenu |
|---|---|
| **Type d'attaque** | **Évasion** (exemples adverses en boîte noire) : le texte toxique est déguisé pour que le modèle ne le reconnaisse plus, sans changer son sens pour un lecteur humain. |
| **Cible** | Le modèle DistilBERT déployé, via la route publique `POST /score`. Le point d'entrée est le champ `text` : c'est la seule chose que l'attaquant contrôle, et il n'a besoin ni du code ni des poids du modèle. |
| **Objectif de l'attaquant** | Publier des insultes, menaces ou propos haineux sans qu'ils soient signalés : obtenir `toxique: false` et un score bas pour un commentaire réellement toxique. |
| **Techniques** | 4 déguisements appliqués aux seuls mots toxiques : **leetspeak** (`idiot` → `1d10t`), **lettres espacées** (`i d i o t`), **homoglyphes** (lettres cyrilliques identiques à l'œil, `іdіоt`), **caractères invisibles** (espace sans chasse U+200B entre les lettres), et un **mélange** des quatre. |
| **Pourquoi elle marche ici** | Le modèle a appris sur des mots bien orthographiés. Le nettoyage du TP1 ne ramène pas ces variantes à leur forme normale ; il transforme même les caractères invisibles en espaces, ce qui revient à l'attaque « lettres espacées ». La doc du TP1 signalait déjà le risque (§ 1.3 : « une insulte déformée (`m0ron`) peut être prise pour un nom »). |
| **Impact technique** | Le rappel s'effondre : la moitié des commentaires toxiques passent (mesuré au § 2). Aucune alerte : le service répond normalement, en 200, avec la même latence. |
| **Impact éthique** | Les personnes visées par le harcèlement ne sont plus protégées. Les propos haineux (`identity_hate`) déguisés touchent des groupes déjà vulnérables. La confiance dans la modération baisse. |
| **Impact RGPD** | Les commentaires qui passent peuvent contenir des données sensibles (Art. 9 : origine, religion, orientation sexuelle) visées par la haine. Les homoglyphes et caractères invisibles contournent aussi les regex d'anonymisation : un e-mail ou un nom déguisé peut ne pas être masqué. |
| **Risque IA Act** | Atteinte à l'exigence de **robustesse** (Art. 15 : résistance aux tentatives de tiers de détourner le système en exploitant ses vulnérabilités). Les données d'entrée sont manipulées pour provoquer une erreur du modèle : c'est l'exemple adverse que cite l'Art. 15 § 5. |

**Pourquoi cette attaque plutôt qu'une autre.** Elle est **réaliste** (n'importe quel utilisateur peut la faire, à la main, sans outil) et **mesurable sans coût** (en local, sur le test officiel). Les autres attaques possibles ont des limites : le **vol du modèle par requêtes** coûte des milliers d'appels à l'API ; l'**empoisonnement des données** demande un réentraînement (64 min par essai) ; la **saturation de l'API** a déjà été testée au TP1 et ne vise pas le modèle.

## 2. Mise en œuvre et mesures (étape 2)

**Protocole.**
- **Échantillon :** 500 commentaires toxiques et 500 non toxiques du test officiel (lignes à -1 exclues, graine 42). Les toxiques sont choisis parmi ceux qui contiennent au moins un mot de la liste de mots toxiques du prétraitement (`api/preprocess.py`) : sans cela, l'attaque n'aurait rien à déguiser.
- **Attaque :** seuls les mots toxiques sont déguisés, le reste du texte est intact. L'attaque est appliquée à tous les textes : un commentaire non toxique peut contenir un gros mot.
- **Chaîne de traitement :** la même que l'API (anonymisation, nettoyage, DistilBERT, seuils par label). Un commentaire est « toxique prédit » si au moins un label dépasse son seuil.
- **Seuils :** ceux de `models/seuils.json`, recalculés sur la validation par `api.export_seuils`.
- **Machine :** Mac M3. La latence inclut le prétraitement et le modèle, sans le réseau.

**Exemple** (`You are a stupid idiot and a moron`), tel que le modèle le reçoit après prétraitement :

| Attaque | Texte reçu par le modèle |
|---|---|
| leetspeak | `you are a 7up1d 1d107 and a m0r0n` |
| espaces | `you are a s t u p i d i d i o t and a m o r o n` |
| homoglyphes | `you are a stuріd іdіоt and a mоrоn` (lettres cyrilliques) |
| invisibles | `you are a s t u p i d i d i o t and a m o r o n` (le nettoyage a changé les invisibles en espaces) |

**Résultats** (DistilBERT, 1 000 commentaires) :

![Attaque par évasion](results/evasion_distilbert.png)

| Variante | Précision | Rappel | Faux positifs | F1 | Évasion | Latence moy. |
|---|---|---|---|---|---|---|
| Sans attaque | 0,93 | **0,92** | 0,068 | 0,93 | — | 15,1 ms |
| Leetspeak | 0,94 | 0,48 | 0,032 | 0,64 | 48 % | 14,4 ms |
| Lettres espacées | 0,96 | **0,40** | 0,016 | 0,56 | **57 %** | 15,8 ms |
| Homoglyphes | 0,96 | 0,49 | 0,022 | 0,65 | 47 % | 14,9 ms |
| Caractères invisibles | 0,96 | **0,40** | 0,016 | 0,56 | **57 %** | 14,3 ms |
| Mélange | 0,94 | 0,46 | 0,028 | 0,61 | 51 % | 14,7 ms |

*Évasion* = part des commentaires toxiques détectés sans attaque qui ne le sont plus avec l'attaque.

**Interprétation.**
- **L'attaque est efficace et bon marché.** Le rappel passe de 0,92 à 0,40-0,49 : **un commentaire toxique sur deux n'est plus détecté**. Il suffit de changer quelques caractères, à la main.
- **La précision ne bouge presque pas (0,93 → 0,94-0,96)**, et c'est trompeur. Le modèle ne se met pas à accuser des textes sains : il se tait. Les **faux positifs baissent même** (0,068 → 0,016), parce que les commentaires sains qui contenaient un gros mot ne sont plus signalés non plus. Une supervision qui ne suivrait que la précision ou le taux d'erreur ne verrait rien.
- **La latence est inchangée** (14-16 ms, différences dans le bruit de mesure) : l'attaque est **invisible** côté performance, et aucune alerte Prometheus de l'étape 6 ne se déclencherait.
- **Les lettres espacées et les caractères invisibles sont les plus efficaces (57 %)** et donnent exactement le même résultat : notre propre nettoyage transforme les caractères invisibles en espaces. Le prétraitement, conçu pour réduire le vocabulaire, aide ici l'attaquant.
- **Le modèle résiste un peu** : environ la moitié des toxiques restent détectés, grâce au contexte (le reste de la phrase reste agressif) et aux sous-mots de DistilBERT, qui reconnaissent parfois des morceaux (`m0r0n` → `m`, `##0`, `##r`…).

**Limites de la mesure.**
- **Échantillon équilibré** (50 % de toxiques, contre environ 10 % dans le vrai test) : la précision y est plus élevée qu'en conditions réelles. Le rappel et le taux d'évasion, eux, ne dépendent pas de cette proportion.
- **Seuls les mots de la liste du prétraitement sont déguisés.** Un attaquant réel déguiserait aussi d'autres mots : l'attaque mesurée est plutôt prudente.
- **Une seule exécution, en local.** Sur l'API déployée, la latence inclurait le réseau (environ 200 ms, TP1 § 5).

---

## 3. Défense contre l'évasion : tableau et graphique avant/après (étape 3)

**Défense implémentée** (`normaliser_anti_evasion`, `api/preprocess.py`) : branchée tout au début du traitement, avant l'anonymisation et le nettoyage existants, sans toucher au modèle. Elle défait les 4 déguisements du § 1-2 : unification Unicode (NFKC), suppression des caractères invisibles, conversion des homoglyphes cyrilliques vers le latin, regroupement des mots espacés lettre par lettre, et dé-leet (uniquement dans les mots contenant déjà une vraie lettre, pour ne pas abîmer un numéro ou une adresse IP).

**Réexécution de l'attaque initiale** (`attack/defense.py`), même protocole, même échantillon que le § 2 (500 + 500 commentaires) :

![Effet de la défense anti-évasion](results/defense_distilbert.png)

| Variante | Rappel sans défense | Rappel avec défense | Taux d'évasion sans défense | Taux d'évasion avec défense |
|---|---|---|---|---|
| Sans attaque | 0,92 | 0,93 | — | — |
| Leetspeak | 0,48 | **0,81** | 48 % | **12 %** |
| Lettres espacées | 0,40 | **0,86** | 57 % | **8 %** |
| Homoglyphes | 0,49 | **0,93** | 47 % | **0 %** |
| Caractères invisibles | 0,40 | **0,93** | 57 % | **0 %** |

**Interprétation.**
- **La défense marche, nettement.** Sur les homoglyphes et les caractères invisibles, le rappel revient exactement au niveau "sans attaque" (0,93) et le taux d'évasion tombe à **0 %** : ces deux déguisements sont entièrement défaits avant que le modèle ne voie le texte.
- **Leetspeak et lettres espacées résistent un peu mieux** (rappel à 0,81-0,86, évasion à 8-12 % au lieu de 0 %) : la règle de dé-leet est volontairement prudente (elle ne touche pas un chiffre isolé comme dans "3pm" ou "v2"), et le regroupement des mots espacés peut rater certains cas limites.
- **Le rappel "sans attaque" ne baisse pas** (0,92 → 0,93) : la défense ne dégrade pas la détection sur du texte normal, c'est le point de vigilance principal pour ce genre de correction.
- **Les faux positifs remontent légèrement sur les variantes attaquées** (ex. homoglyphes : 0,022 → 0,068), mais rejoignent exactement le taux de base "sans attaque" (0,068) : c'est cohérent — la défense traite un commentaire sain déguisé comme un commentaire sain normal, ni mieux ni moins bien.

**Limite assumée :** testée sur le même échantillon équilibré que le § 2 (voir ses limites), et seulement sur les 4 variantes individuelles, pas sur le mélange des 4 à la fois.

---

## 4. Dashboard inter-équipes : 4 attaques contre les API des autres groupes

En plus de l'attaque sur notre propre modèle (§ 1-2, le livrable officiel du TP), on a construit un outil pour tester les mêmes familles d'attaque contre les API **déployées par d'autres groupes**, avec leur accord et leur clé API. Scripts : [serveur.py](serveur.py) (serveur local FastAPI + flux SSE) et [dashboard.html](dashboard.html) (page de suivi en direct).

Les 4 attaques sont communes aux trois groupes :

| Attaque | Principe | Requêtes par commentaire |
|---|---|---|
| **Déguisement** | Leetspeak + lettres cyrilliques (homoglyphes) + caractères invisibles (U+200B) sur les mots toxiques. Le texte reste lisible par un humain, mais casse la tokenisation. | 1 |
| **Noyage** | Place le commentaire toxique après un pavé d'environ 4 000 caractères de texte neutre. Exploite la troncature du contexte : si le modèle ne regarde que les N premiers tokens, le commentaire toxique placé à la fin n'est jamais vu. | 1 |
| **Recherche de synonymes** | Recherche gloutonne : essaie mot par mot un synonyme ou une faute de frappe, garde la substitution si le score baisse, s'arrête dès que le verdict bascule. | ≤ 15 (budget plafonné) |
| **Mutation aléatoire** | Modifie un caractère au hasard dans un mot, garde la mutation si le score baisse, recommence depuis la meilleure version trouvée. | ≤ 15 (budget plafonné) |

Testées sur les mêmes 15 commentaires toxiques + 15 sains (voir [attack/phrases.csv](phrases.csv)), le 2026-11-16.

Des rapports autonomes et indépendants (sans comparaison entre eux) existent aussi, pour être envoyés tels quels à chaque équipe afin de nourrir leur propre étape 3 : [rapport_florentin_gilane.md](rapport_florentin_gilane.md), [rapport_aurel_baunell.md](rapport_aurel_baunell.md), [rapport_exauce_gilbert.md](rapport_exauce_gilbert.md). Ce qui suit est notre lecture à nous, en interne, avec les trois résultats réunis.

### 4.1 Florentin & Gilane (`<adresse retirée>`)

![Détection avant/après par attaque — Florentin & Gilane](resultats_equipes/florentin_resultats.png)

| Attaque | Rappel avant | Rappel après | Évasions | Latence moyenne |
|---|---|---|---|---|
| Déguisement | 93 % | 60 % | 5 / 15 | 80 ms |
| **Noyage** | 93 % | **0 %** | **14 / 15** | 100 ms |
| Recherche de synonymes | 93 % | 87 % | 1 / 15 | 398 ms |
| Mutation aléatoire | 93 % | 60 % | 5 / 15 | 264 ms |

**Déguisement (5/15 évasions) :**

| Commentaire original | Texte envoyé | Score avant | Score après |
|---|---|---|---|
| You are a stupid idiot and everyone hates you | уоu 4r3 4 s​t​u​р​i​d 1​d​і​0​7 аnd 3​v​3​r​у​o​n​е h​4​t​e​$ yоu | 100 | 49 |
| What a worthless loser you really are | W​h​а​7 4 w​0​r​t​h​l​е​s​$ l​o​$​3​r уou r​3​4​l​l​у аrе | 94 | 5 |
| Everyone thinks you are a complete joke | е​v​3​r​y​0​n​3 t​h​і​n​k​s y0u аr3 4 с​о​m​p​l​3​7​е j​о​k​3 | 97 | 38 |
| Call me at +33 6 12 34 56 78 you pathetic loser... | с​а​l​l m3 47 +33 6 12 34 56 78 yоu р​а​t​h​3​t​1​c l​0​s​3​r $о I c4n с​u​r​s​e у0u оut | 99 | 13 |
| Worthless clown, my IP is 192.168.1.42... | W​o​r​7​h​l​3​$​s с​l​o​w​n​, mу ір 1s 1​9​2​.​1​6​8​.​1​.​4​2 c​0​m​3 f​і​g​h​7 m3 іf уou d​4​r​е | 88 | 42 |

**Noyage (14/15) :** texte envoyé = commentaire précédé d'environ 4 000 caractères de texte neutre ; score à 3 pour 14 des 15 commentaires, quel que soit leur contenu — détail complet dans [resultats_equipes/florentin_evasions.csv](resultats_equipes/florentin_evasions.csv).

**Synonymes (1/15) :** une seule évasion, `"You stupid idiot, contact me at john.doe@example.com..."`, score 95 → 48 après `stupid`→`stuid`, `idiot`→`fool`.

**Leur point faible :** la troncature du contexte (noyage, 93 %→0 %). **Leur point fort :** la robustesse sémantique (synonymes, seulement 1 évasion).

### 4.2 Exauce & Gilbert (`<adresse retirée>`)

![Détection avant/après par attaque — Exauce & Gilbert](resultats_equipes/exauce_resultats.png)

| Attaque | Rappel avant | Rappel après | Évasions | Latence moyenne |
|---|---|---|---|---|
| Déguisement | 60 % | 7 % | 9 / 15 | 81 ms |
| **Noyage** | 60 % | **0 %** | **9 / 15** | 119 ms |
| **Recherche de synonymes** | 60 % | **0 %** | **9 / 15** | 234 ms |
| Mutation aléatoire | 60 % | 13 % | 7 / 15 | 161 ms |

**Rappel de base déjà faible (60 %) avant toute attaque** — 5-6 commentaires toxiques passaient inaperçus sans manipulation. Les 9 mêmes commentaires tombent avec le déguisement, le noyage **et** la recherche de synonymes :

| Commentaire original | Déguisement → | Synonymes → | Score avant |
|---|---|---|---|
| You are a stupid idiot and everyone hates you | 10,8 | 48,8 | 59,6 |
| Shut up you pathetic moron nobody cares about you | 41,0 | 48,9 | 56,9 |
| Get lost you disgusting piece of garbage | 41,1 | 43,1 | 59,6 |
| You people are all brainless fools | 33,9 | 21,2 | 55,2 |
| Stop talking you insufferable idiot | 38,0 | 47,8 | 56,2 |
| You stupid idiot, contact me at john.doe@example.com... | 37,2 | 41,6 | 57,2 |
| Shut up moron, I know you live at 221B Baker Street... | 46,5 | 33,9 | 75,2 |
| Call me at +33 6 12 34 56 78 you pathetic loser... | 8,2 | 47,0 | 50,1 |
| Hey @johnsmith99 you disgusting freak everyone... | 35,7 | 48,2 | 55,0 |

**Le plus préoccupant chez eux : la recherche de synonymes atteint 0 % de rappel.** Contrairement au déguisement, elle change le sens des mots sans aucune faute — signe que leur modèle s'appuie sur des mots-clés plutôt que sur le sens global de la phrase. Leur API ne renvoie d'ailleurs pas de verdict explicite (`label`), juste un `score` — seuil de 50 utilisé par analogie avec la nôtre.

### 4.3 Aurel & Baunell (`<adresse retirée>`)

**Pas encore de résultats.** Leur API est en HTTPS sur IP brute avec un certificat qui ne passe la vérification standard ni avec `curl` ni avec `requests`. Décision prise : désactiver la vérification TLS pour ce groupe seulement (`VERIFIER_TLS_AUREL=0`), explicitement plutôt que par défaut — en attente que le serveur tourne avec ce réglage pour lancer les 4 attaques.

### 4.4 Ce qui ressort, toutes équipes confondues

**Le noyage est systématiquement l'attaque la plus dévastatrice** chez les deux groupes testés (14/15 et 9/15, soit évasion totale pour Exauce & Gilbert) — et pour une seule requête par commentaire, contre jusqu'à 15 pour les attaques itératives. Voir § 5 : c'est aussi vrai pour notre propre modèle.

---

## 5. Synthèse interne — ce qu'on garde pour nous

Cette section n'est **pas** destinée aux autres groupes : c'est la lecture croisée de tout ce qu'on a mesuré, pour décider quoi corriger en priorité sur **notre propre** API avant l'étape 3.

### 5.1 Comparaison des 4 attaques, toutes cibles confondues

| Attaque | Notre modèle (local, § 1-2) | Florentin & Gilane | Exauce & Gilbert |
|---|---|---|---|
| Déguisement | 48-57 % d'évasion (1 000 commentaires) | 5/15 évasions | 9/15 évasions |
| **Noyage** | **Testé le 2026-11-16, voir § 5.2 : évasion nette** | **14/15 évasions** | **9/15 (évasion totale)** |
| Recherche de synonymes | Non testé sur notre modèle | 1/15 évasion | 9/15 (évasion totale) |
| Mutation aléatoire | Non testé sur notre modèle | 5/15 évasions | 7/15 évasions |

**Le noyage est systématiquement la plus dévastatrice des quatre attaques, chez les trois cibles testées.** Ce n'est pas une coïncidence : les trois utilisent des modèles transformer (vraisemblablement DistilBERT ou équivalent) avec une longueur de contexte fixe.

### 5.2 Alerte : notre propre API a la même faille

**Vérifié le 2026-11-16, en local, avec notre propre `api/modeles.py` :** notre DistilBERT tronque l'entrée à **128 tokens** (`LONGUEUR_BERT = 128`, `truncation=True` dans `ModeleDistilBERT.probabilites`). Le même texte de noyage qui fait tomber les autres équipes fait tomber le nôtre :

| | Probabilité `toxic` |
|---|---|
| `"You are a stupid idiot and everyone hates you"` seul | 0,995 — détecté |
| Même phrase noyée dans ~4 000 caractères de texte neutre placés avant | **0,012 — passe** |

**C'est la priorité n°1 pour notre propre étape 3 (défense), avant même de regarder ce que les autres groupes nous renvoient.** Pistes déjà identifiées dans les rapports envoyés aux autres équipes, applicables chez nous à l'identique :
- Refuser (HTTP 422) un texte dépassant une longueur raisonnable, plutôt que de le tronquer silencieusement à 128 tokens.
- Ou segmenter le texte en plusieurs fenêtres et agréger les scores (max ou moyenne), plutôt qu'une seule passe tronquée.

### 5.3 Travail restant

- **Tester noyage, recherche de synonymes et mutation aléatoire sur notre propre API déployée** (pas seulement en local comme au § 5.2), avec le même protocole que pour les autres groupes — on n'a pour l'instant que le déguisement en conditions complètes (§ 1-2).
- **Corriger la troncature** (§ 5.2) et mesurer l'effet du correctif avec le même script, pour avoir un avant/après chiffré à présenter à l'étape 3.
- Compléter le rapport Aurel & Baunell dès que leur connexion HTTPS est réglée côté serveur.

---

## 6. Attaque reçue : vol de modèle (étape 3 — défense)

**Constat :** une autre équipe a attaqué notre API déployée (cluster `dss-api`) par **extraction de modèle** — requêtes massives (jusqu'à 2000, sans limite de débit observée), pour entraîner un clone à partir de nos réponses. Impact qu'ils ont mesuré de leur côté : clone à 94,7 % d'accord avec notre API, notre latence qui double sous la charge (245 ms → 473-795 ms), quelques erreurs 502. Cette attaque est la plus pertinente pour notre défense : c'est celle qu'on a **réellement reçue**, pas une hypothèse.

**Division du travail :** la limitation de débit (rate limiting) et la gestion de la clé API sont traitées par Enzo, côté déploiement. Notre contribution porte sur **ce que l'API révèle par requête** — une piste de défense indépendante du débit.

### 6.1 Défense testée : quantifier le score renvoyé

**Hypothèse :** l'attaque marche bien parce que l'API renvoie un score très précis (probabilités à 4 décimales par label). Réduire cette précision devrait appauvrir le signal que l'attaquant utilise pour entraîner son clone (distillation), sans rien changer au modèle ni au débit.

**Défense implémentée** (`api/defense_extraction.py`) : `quantifier_score()`, qui arrondit le score renvoyé. Testée à deux granularités : arrondi à la dizaine, puis arrondi au tout-ou-rien (verdict binaire pur, 0 ou 100 — aucune nuance du tout).

**Protocole de test** (`attack/extraction.py`) : on simule l'attaquant. Il envoie N textes (100 à 2000, sans leurs vrais labels) à notre modèle local, récupère les scores (bruts ou quantifiés selon la condition), entraîne un clone (TF-IDF + régression Ridge par label) sur ces scores, puis on évalue l'accord clone/cible sur 3 000 commentaires étiquetés séparément — même méthode que celle utilisée par l'équipe qui nous a attaqués.

### 6.2 Résultat — la défense ne marche pas chez nous

![Effet de la quantification sur la fidélité du clone](results/extraction.png)

| Requêtes | Accord clone/cible — sans défense | Accord clone/cible — avec défense (binaire) |
|---|---|---|
| 100 | 0,940 | 0,940 |
| 500 | 0,940 | 0,940 |
| 1 000 | 0,942 | 0,942 |
| 2 000 | 0,944 | 0,944 |

**Même en ne renvoyant plus aucune nuance (verdict 0/100 pur, zéro information de confiance), le clone reste aussi fidèle.** Les deux courbes se superposent exactement.

**Pourquoi.** Le vocabulaire toxique est très discriminant (`idiot`, `moron`, insultes directes...) : un simple TF-IDF sépare déjà très bien les deux classes. L'attaquant n'a pas besoin du score précis pour retrouver la frontière de décision — le label seul lui suffit presque autant. **Réduire l'information par requête n'est donc pas une défense efficace pour ce type de modèle.** C'est un résultat négatif honnête, pas un échec de la mesure : deux granularités testées (dizaine, puis binaire pur), même constat aux deux.

### 6.3 Conclusion : la quantification ne suffit pas → défense par limitation de débit

**La vraie défense contre cette attaque, chez nous, c'est le débit — pas le contenu de la réponse.** Si le clone atteint déjà 94 % d'accord avec seulement 100 requêtes (§ 6.2), aucune limitation du contenu ne compense une absence de limitation du nombre d'appels. C'est cette défense qu'on a implémentée et testée.

**Implémentation** (`api/limiteur_debit.py`, branché dans `api/main.py` sur la route `/predire`) : fenêtre glissante, quota configurable par variable d'environnement (`DEBIT_MAX_REQUETES`, `DEBIT_FENETRE_S`), rejet HTTP 429 avec `Retry-After` dès que le quota est dépassé. En local, faute de clé API, on limite par adresse IP — en production (avec clé), il faudrait limiter par clé, pour qu'un client légitime partageant une IP ne soit pas pénalisé par un autre.

**Test réel** (`attack/debit.py`) : rafale de requêtes HTTP pendant 20 s contre l'API locale en cours d'exécution, avec et sans le limiteur actif.

![Effet du limiteur de débit](results/debit.png)

| | Sans limiteur | Avec limiteur (60 req / 60 s) |
|---|---|---|
| Requêtes exploitables obtenues (200 OK) en 20 s | **1 442** | **60** |
| Requêtes rejetées (429) | 0 | 30 507 |
| Débit de tentatives de l'attaquant | 72 req/s | 1 528 req/s (rejets quasi gratuits, avant le modèle) |

**Effet concret.** Sans limite, un attaquant obtient en 20 secondes largement de quoi entraîner un clone à 94 % de fidélité (le seuil de 100 requêtes est atteint en moins de 2 s). Avec la limite à 60 requêtes/minute, il lui faudrait environ **33 minutes** pour réunir les 2 000 requêtes utilisées par l'attaque reçue — largement le temps de détecter un usage anormal et de révoquer la clé, et ça empêche directement l'effet de surcharge (latence doublée, erreurs 502) observé lors de l'incident réel (§ 6, constat).

**Limite assumée :** le quota ne rend pas le vol de modèle impossible (un attaquant patient sur plusieurs heures peut toujours réunir assez de requêtes), mais il le ralentit radicalement, le rend détectable, et supprime l'effet de surcharge du service — ce que la quantification du score (§ 6.2) ne faisait pas du tout.


---

## 7. Défense contre le noyage : fenêtres glissantes (étape 3)

**Vulnérabilité identifiée (§ 5.2).** Notre modèle DistilBERT ne regarde que les **128 premiers tokens** d'un texte (troncature droite par défaut du tokenizer HuggingFace). L'attaque noyage envoie plusieurs milliers de caractères neutres *avant* la phrase toxique : le contenu toxique est alors coupé et le modèle ne voit que du neutre — il répond `toxique: false`.

**Défense implémentée** (`api/modeles.py`, méthode `ModeleDistilBERT.probabilites` et `ModeleBiLSTM.probabilites`) : scan en **fenêtres glissantes** de 128 tokens (DistilBERT) ou 200 mots (BiLSTM). Pour un texte court (≤ seuil), une seule passe comme avant. Pour un texte long, on découpe en fenêtres consécutives sans chevauchement et on retourne la **probabilité maximale** observée sur toutes les fenêtres. Le contenu toxique est détecté peu importe sa position dans le texte.

**Coût de la défense.** Sur les textes courants (< 128 tokens) il n'y a aucun surcost : une seule passe. Le nombre de passes croît linéairement avec la longueur uniquement pour les textes anormalement longs, qui représentent typiquement moins de 1 % du trafic réel.

**Réexécution** (`attack/defense_noyage.py`) : 5 phrases toxiques, 5 niveaux de rembourrage neutre (0 → 4 000 caractères), mesuré localement sur DistilBERT.

![Défense anti-noyage](results/defense_noyage.png)

| Rembourrage neutre ajouté | Proba toxic sans défense | Proba toxic avec défense | Évasion sans défense | Évasion avec défense |
|---|---|---|---|---|
| 0 car. (texte normal) | **0,986** | **0,986** | 0 % | 0 % |
| 500 car. | 0,904 | 0,904 | 0 % | 0 % |
| 1 000 car. | 0,096 | **0,926** | **100 %** | **0 %** |
| 2 000 car. | 0,096 | **0,942** | **100 %** | **0 %** |
| 4 000 car. | 0,096 | **0,917** | **100 %** | **0 %** |

**Interprétation.**
- **L'attaque est neutralisée à partir de 1 000 caractères de rembourrage** : sans défense, la probabilité chute à 0,096 (sous le seuil 0,5, évasion = 100 %) ; avec défense, elle reste à 0,92-0,94 (évasion = 0 %) quel que soit le volume de rembourrage.
- **Sous 500 caractères**, les deux donnent le même résultat (0,90) : à ce niveau, le texte toxique tient encore dans la fenêtre de 128 tokens et aucune défense n'est nécessaire.
- **Le comportement normal est préservé** : sur un texte sans rembourrage (0 car.), la proba reste exactement à 0,986 — la défense ne dégrade pas la détection habituelle.
