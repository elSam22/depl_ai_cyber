"""TP2, étape 3 : défense contre le vol de modèle (extraction) reçu sur notre API.

Le vol de modèle marche parce que l'API renvoie une information très riche par requête :
le score exact (ex. 98,4) et les 6 probabilités à 4 décimales. Un attaquant entraîne alors
un clone sur ces réponses (distillation) et obtient une copie fidèle en très peu de requêtes.

Défense : réduire ce que chaque réponse révèle, sans toucher au modèle ni au débit
(la limitation de débit est traitée séparément, côté déploiement). On arrondit le score à
la dizaine la plus proche (quantification) au lieu de renvoyer la valeur exacte : l'attaquant
reçoit toujours un verdict utilisable, mais un signal beaucoup plus pauvre pour entraîner
un clone par distillation.
"""


def quantifier_score(score: float, pas: int = 10) -> int:
    """Arrondit un score 0-100 au multiple de `pas` le plus proche (défaut : dizaine).
    Ex. 98,4 -> 100 ; 63,7 -> 60. Perd l'information fine, garde le verdict global."""
    return int(round(score / pas) * pas)
