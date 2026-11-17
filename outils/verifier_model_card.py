"""Contrôle de model_card.json (conformité IA Act, TP2 étape 4) : lancé par la pipeline à chaque push.

    python outils/verifier_model_card.py [chemin]      # par défaut : model_card.json à la racine

Vérifie les champs imposés par le sujet, la catégorie de risque (quatre niveaux du règlement), le format de la date et,
surtout, qu'aucune affirmation n'est faite sans preuve : `bias_detected` ne peut être `false` que si une évaluation
est décrite ; s'il vaut `null` (non évalué), une `bias_note` doit le dire.
"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

CHEMIN = Path(sys.argv[1] if len(sys.argv) > 1 else "model_card.json")
NIVEAUX = {"unacceptable", "high", "limited", "minimal"}      # inacceptable, haut, limité, minimal
CHAMPS_TEXTE = ["model_name", "description", "risk_level", "data_source", "version", "last_update"]

erreurs = []
try:
    carte = json.loads(CHEMIN.read_text(encoding="utf-8"))
except (OSError, ValueError) as e:
    sys.exit(f"ECHEC : {CHEMIN} illisible ou invalide ({e})")

for champ in CHAMPS_TEXTE:
    if not isinstance(carte.get(champ), str) or not carte[champ].strip():
        erreurs.append(f"« {champ} » manquant ou vide")
if carte.get("risk_level") not in NIVEAUX:
    erreurs.append(f"« risk_level » doit valoir l'un de {sorted(NIVEAUX)} (valeur : {carte.get('risk_level')!r})")
elif not str(carte.get("risk_justification", "")).strip():
    erreurs.append("« risk_justification » manquant : la catégorie de risque doit être justifiée")
mesures = carte.get("privacy_measures")
if not (isinstance(mesures, list) and mesures and all(isinstance(m, str) and m.strip() for m in mesures)):
    erreurs.append("« privacy_measures » doit être une liste non vide de textes")
try:
    jour = datetime.strptime(str(carte.get("last_update")), "%Y-%m-%d").date()
    if jour > date.today():
        erreurs.append(f"« last_update » est dans le futur ({jour})")
except ValueError:
    erreurs.append("« last_update » doit être une date AAAA-MM-JJ")
biais = carte.get("bias_detected", "absent")
if biais not in (True, False, None):
    erreurs.append("« bias_detected » doit valoir true, false ou null (non évalué)")
elif biais is None and not str(carte.get("bias_note", "")).strip():
    erreurs.append("« bias_detected » est null (non évalué) : « bias_note » doit expliquer pourquoi")
elif biais is False and not carte.get("bias_evaluation"):
    erreurs.append("« bias_detected » vaut false sans « bias_evaluation » : une absence de biais doit être démontrée")

if erreurs:
    print(f"ECHEC : {CHEMIN}")
    for e in erreurs:
        print("  -", e)
    sys.exit(1)
print(f"OK : {CHEMIN} (risque « {carte['risk_level']} », version {carte['version']}, biais : "
      f"{'non évalué' if biais is None else biais})")
