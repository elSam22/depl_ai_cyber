# Rapport d'attaque — API Digital Social Score (Aurel & Baunell)

TP2, étape 2 : attaque prévue contre votre API déployée (`<adresse retirée>`), avec votre accord et votre clé API — 15 commentaires toxiques + 15 commentaires sains, 4 familles d'attaque. **Pas encore exécutée au moment de ce rapport**, voir § 2.

## 1. Les 4 attaques prévues

| Attaque | Principe | Requêtes par commentaire |
|---|---|---|
| **Déguisement** | Leetspeak + lettres cyrilliques (homoglyphes) + caractères invisibles (U+200B) sur les mots toxiques. Le texte reste lisible par un humain, mais casse la tokenisation. | 1 |
| **Noyage** | Place le commentaire toxique après un pavé d'environ 4 000 caractères de texte neutre. Exploite la troncature du contexte : si le modèle ne regarde que les N premiers tokens, le commentaire toxique placé à la fin n'est jamais vu. | 1 |
| **Recherche de synonymes** | Recherche gloutonne : essaie mot par mot un synonyme ou une faute de frappe, garde la substitution si le score baisse, s'arrête dès que le verdict bascule. | ≤ 15 (budget plafonné) |
| **Mutation aléatoire** | Modifie un caractère au hasard dans un mot, garde la mutation si le score baisse, recommence depuis la meilleure version trouvée. | ≤ 15 (budget plafonné) |

## 2. Pourquoi il n'y a pas encore de résultats

Votre API est en HTTPS sur une adresse IP brute, et son certificat ne passe la vérification standard ni avec `curl`, ni avec la bibliothèque Python `requests` — deux clients indépendants, donc ce n'est pas un problème de notre côté. Avant de contourner ça, trois options ont été envisagées : obtenir un domaine avec certificat valide (type `sslip.io`), basculer sur une route HTTP si elle existe, ou désactiver la vérification TLS pour ce test précis. La troisième a été retenue, **explicitement** plutôt que par défaut.

**À faire dès que le test tourne** : remplacer cette section par le même tableau de résultats que les deux autres rapports (rappel avant/après par attaque, évasions, latence) et un graphique équivalent.

## 3. Une piste de défense à vérifier dès maintenant

Le noyage (§ 1) exploite une faiblesse d'architecture précise : la troncature du contexte à une longueur fixe de tokens. C'est une chose à vérifier indépendamment du résultat du test : **votre modèle tronque-t-il l'entrée à une longueur fixe, et si oui, refuse-t-il ou segmente-t-il un texte plus long que cette limite ?** Si ce n'est pas le cas aujourd'hui, c'est une défense simple à mettre en place avant même d'avoir vu le résultat de l'attaque.
