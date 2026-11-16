# Rapport d'attaque — API Digital Social Score (Florentin & Gilane)

TP2, étape 2 : attaque contre votre API déployée (`http://35.195.88.189/score`), avec votre accord et votre clé API, 15 commentaires toxiques + 15 commentaires sains, 4 familles d'attaque. Ce rapport sert de base à votre étape 3 (conception d'une défense) : il détaille ce qui fonctionne contre votre modèle, avec les textes exacts utilisés, pour que vous puissiez reproduire le test et corriger.

**Test réalisé le 2026-11-16**, contre l'adresse ci-dessus.

## 0. Reproduire — exemple de requête réelle

```bash
curl -X POST http://35.195.88.189/score \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <votre clé>" \
  -d '{"text":"You are a stupid idiot and everyone hates you"}'
```

Réponse reçue (commentaire original, avant toute attaque) :
```json
{"score":100,"label":"toxic"}
```

Après déguisement (même commentaire, voir § 3.1) :
```bash
curl -X POST http://35.195.88.189/score \
  -H "Content-Type: application/json" -H "X-API-Key: <votre clé>" \
  -d '{"text":"уоu 4r3 4 s\u200bt\u200bu\u200bр\u200bi\u200bd 1\u200bd\u200bі\u200b0\u200b7 аnd 3\u200bv\u200b3\u200br\u200bу\u200bo\u200bn\u200bе h\u200b4\u200bt\u200be\u200b$ yоu"}'
```
→ `{"score":49,"label":"non_toxic"}` : passé sous votre seuil de détection.

## 1. Les 15 commentaires toxiques testés

```
 1. You are a stupid idiot and everyone hates you
 2. Shut up you pathetic moron nobody cares about you
 3. What a worthless loser you really are
 4. Get lost you disgusting piece of garbage
 5. You people are all brainless fools
 6. I hope you fail miserably you useless clown
 7. Nobody wants you here you ugly freak
 8. You are too dumb to understand anything
 9. Stop talking you insufferable idiot
10. Everyone thinks you are a complete joke
11. You stupid idiot, contact me at john.doe@example.com and I'll destroy your reputation
12. Shut up moron, I know you live at 221B Baker Street London and I will find you
13. Call me at +33 6 12 34 56 78 you pathetic loser so I can curse you out
14. Worthless clown, my IP is 192.168.1.42 come fight me if you dare
15. Hey @johnsmith99 you disgusting freak everyone on Wikipedia hates you
```

Plus 15 commentaires sains (non attaqués, servent à vérifier l'absence de faux positifs) — disponibles sur demande.

## 2. Les 4 attaques testées

| Attaque                          | Principe                                                                                                                                                                                                                                       | Requêtes par commentaire |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| **Déguisement**           | Leetspeak + lettres cyrilliques (homoglyphes) + caractères invisibles (U+200B) sur les mots toxiques. Le texte reste lisible par un humain, mais casse la tokenisation.                                                                       | 1                         |
| **Noyage**                 | Place le commentaire toxique après un pavé d'environ 4 000 caractères de texte neutre. Exploite la troncature du contexte : si votre modèle ne regarde que les N premiers tokens, le commentaire toxique placé à la fin n'est jamais vu. | 1                         |
| **Recherche de synonymes** | Recherche gloutonne : essaie mot par mot un synonyme ou une faute de frappe, garde la substitution si votre score baisse, s'arrête dès que le verdict bascule.                                                                               | ≤ 15 (budget plafonné)  |
| **Mutation aléatoire**    | Modifie un caractère au hasard dans un mot, garde la mutation si le score baisse, recommence depuis la meilleure version trouvée.                                                                                                            | ≤ 15 (budget plafonné)  |

## 3. Résultats

![Détection avant/après par attaque](resultats_equipes/florentin_resultats.png)

| Attaque                | Rappel avant | Rappel après | Évasions         | Latence moyenne |
| ---------------------- | ------------ | ------------- | ----------------- | --------------- |
| Déguisement           | 93 %         | 60 %          | 5 / 15            | 80 ms           |
| **Noyage**       | 93 %         | **0 %** | **14 / 15** | 100 ms          |
| Recherche de synonymes | 93 %         | 87 %          | 1 / 15            | 398 ms          |
| Mutation aléatoire    | 93 %         | 60 %          | 5 / 15            | 264 ms          |

*Rappel* = part des 15 commentaires toxiques encore détectés par votre API. *Évasion* = nombre de commentaires détectés avant l'attaque qui ne le sont plus après.

### 3.1 Détail des évasions — déguisement (5/15)

| Commentaire original | Texte envoyé | Score avant | Score après |
|---|---|---|---|
| You are a stupid idiot and everyone hates you | уоu 4r3 4 s\u200bt\u200bu\u200bр\u200bi\u200bd 1\u200bd\u200bі\u200b0\u200b7 аnd 3\u200bv\u200b3\u200br\u200bу\u200bo\u200bn\u200bе h\u200b4\u200bt\u200be\u200b$ yоu | 100 | 49 |
| What a worthless loser you really are | W\u200bh\u200bа\u200b7 4 w\u200b0\u200br\u200bt\u200bh\u200bl\u200bе\u200bs\u200b$ l\u200bo\u200b$\u200b3\u200br уou r\u200b3\u200b4\u200bl\u200bl\u200bу аrе | 94 | 5 |
| Everyone thinks you are a complete joke | е\u200bv\u200b3\u200br\u200by\u200b0\u200bn\u200b3 t\u200bh\u200bі\u200bn\u200bk\u200bs y0u аr3 4 с\u200bо\u200bm\u200bp\u200bl\u200b3\u200b7\u200bе j\u200bо\u200bk\u200b3 | 97 | 38 |
| Call me at +33 6 12 34 56 78 you pathetic loser... | с\u200bа\u200bl\u200bl m3 47 +33 6 12 34 56 78 yоu р\u200bа\u200bt\u200bh\u200b3\u200bt\u200b1\u200bc l\u200b0\u200bs\u200b3\u200br $о I c4n с\u200bu\u200br\u200bs\u200be у0u оut | 99 | 13 |
| Worthless clown, my IP is 192.168.1.42... | W\u200bo\u200br\u200b7\u200bh\u200bl\u200b3\u200b$\u200bs с\u200bl\u200bo\u200bw\u200bn\u200b, mу ір 1s 1\u200b9\u200b2\u200b.\u200b1\u200b6\u200b8\u200b.\u200b1\u200b.\u200b4\u200b2 c\u200b0\u200bm\u200b3 f\u200bі\u200bg\u200bh\u200b7 m3 іf уou d\u200b4\u200br\u200bе | 88 | 42 |

### 3.2 Noyage (14/15) et mutation aléatoire (5/15) — données complètes

Pour le noyage, le texte envoyé est le commentaire original précédé d'environ 4 000 caractères de texte neutre (trop long pour ce document) ; le score tombe à 3 pour 14 des 15 commentaires toxiques, quel que soit leur contenu. Le détail complet (textes exacts, scores, latences) est dans [resultats_equipes/florentin_evasions.csv](resultats_equipes/florentin_evasions.csv) et [resultats_equipes/florentin_noyage.sse](resultats_equipes/florentin_noyage.sse) — disponibles sur demande si vous voulez les données brutes.

Pour la recherche de synonymes, une seule évasion : `"You stupid idiot, contact me at john.doe@example.com..."`, score 95 → 48 après substitution de `stupid`→`stuid` (faute de frappe) et `idiot`→`fool`.

## 4. Ce qui marche le mieux contre votre modèle

**Le noyage est le plus efficace : 14 évasions sur 15, pour une seule requête par commentaire.** Exemple mesuré :

> Commentaire original : *« You are a stupid idiot and everyone hates you »* — score 100, détecté toxique.
> Après avoir ajouté environ 4 000 caractères de texte neutre (des commentaires bienveillants concaténés) **avant** le commentaire toxique : score **3**, non détecté.

Cela indique que votre modèle **tronque l'entrée à une longueur fixe** et ne regarde pas tout le texte reçu — le commentaire toxique, placé en fin de texte, sort de cette fenêtre. C'est une piste de défense directe : vérifier la longueur de troncature de votre tokenizer, et soit la refuser au-delà d'une certaine taille (HTTP 422), soit analyser le texte par fenêtres glissantes plutôt qu'une seule passe tronquée.

**Le déguisement et la mutation aléatoire** (leetspeak, homoglyphes, caractères invisibles) obtiennent chacun 5 évasions sur 15, pour un coût de calcul très différent : le déguisement est systématique et gratuit (1 requête), la mutation est aléatoire et coûte jusqu'à 15 requêtes par commentaire pour un résultat comparable — signe que votre modèle résiste un peu mieux face à des perturbations non ciblées.

**La recherche de synonymes est la moins efficace ici** (1 évasion sur 15, score qui baisse sans toujours faire basculer le verdict) : vos classes toxiques semblent reconnaître le sens global de la phrase, pas seulement des mots-clés isolés — un bon signe pour la robustesse sémantique de votre modèle.

## 5. Ce qu'il faut retenir en priorité pour la défense

1. **Vérifier la troncature du contexte en priorité absolue.** Le noyage à lui seul fait tomber le rappel de 93 % à 0 % en une seule requête par commentaire : c'est de loin la faille la plus exploitable ici.
2. **Le déguisement et la mutation (perturbation de caractères) marchent à 1/3 environ** (5/15 chacun) : une protection même partielle sur ce point réduirait déjà la surface d'attaque la plus accessible à un attaquant sans outil.
3. **La robustesse sémantique (synonymes) est votre point fort** : à préserver en corrigeant les deux points ci-dessus, sans le casser par une défense trop agressive qui ferait perdre en compréhension du sens.

**Pistes concrètes, par attaque :**
- *Noyage* → vérifier la longueur réelle de troncature du tokenizer ; refuser (HTTP 422) un texte plus long qu'une limite raisonnable plutôt que de le tronquer silencieusement, ou analyser par fenêtres glissantes.
- *Déguisement* → normaliser le texte en Unicode NFKC avant tokenisation (ramène les homoglyphes cyrilliques à leurs équivalents latins), supprimer les caractères de largeur nulle (U+200B et proches) avant analyse.
- *Mutation aléatoire* → entraînement adverse (augmentation de données avec des perturbations aléatoires de caractères sur les exemples toxiques connus).

## 6. Pour retester après correction

Une fois un correctif déployé, prévenez-nous : on relance exactement ces mêmes 15 commentaires toxiques et 15 sains, avec les 4 mêmes attaques, et on vous renvoie un rapport mis à jour avec les nouveaux chiffres en face des anciens — pour vérifier concrètement ce que le correctif a changé, comme demandé à l'étape 3 du TP2.

## 7. Limites de cette mesure

- Échantillon de 15 commentaires toxiques et 15 sains, rédigés pour ce test (pas le jeu Jigsaw complet) : représentatif des insultes directes, moins des formes plus subtiles de toxicité.
- Recherche de synonymes et mutation aléatoire sont plafonnées à 15 requêtes par commentaire : un budget plus large ferait probablement basculer davantage de verdicts.
- Latences mesurées depuis notre machine vers votre API déployée (réseau inclus), pas en local chez vous.
