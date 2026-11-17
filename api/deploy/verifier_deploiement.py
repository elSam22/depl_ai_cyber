"""Contrôle de l'API déployée : à lancer après chaque déploiement (script manuel ET pipeline).

    API_KEY=<clé> python api/deploy/verifier_deploiement.py https://<adresse>

Il échoue (code 1) si l'API répond avec le MODÈLE FACTICE (model_version « dummy-… »), ce qui arrive quand l'image est
construite sans les poids : l'API répond alors 200 partout mais ses scores sont faux (incident du 13 novembre).
Utilise uniquement la bibliothèque standard.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("API_URL", "")).rstrip("/")
CLE = os.environ.get("API_KEY", "")
if not URL or not CLE:
    sys.exit("Usage : API_KEY=<clé> python verifier_deploiement.py https://<adresse>")
if not URL.startswith(("https://", "http://")):       # urlopen accepterait aussi file:// : on refuse tout autre schéma
    sys.exit("L'adresse doit commencer par https:// (ou http:// en test local)")


def appel(chemin, corps=None, cle=CLE):
    entetes = {"Content-Type": "application/json"}
    if cle is not None:
        entetes["X-API-Key"] = cle
    requete = urllib.request.Request(URL + chemin, data=json.dumps(corps).encode() if corps is not None else None,
                                     headers=entetes, method="POST" if corps is not None else "GET")
    try:
        with urllib.request.urlopen(requete, timeout=30) as r:   # nosec B310
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


echecs = []
def verifie(condition, message):
    print(("OK      " if condition else "ECHEC   ") + message)
    if not condition:
        echecs.append(message)


# 1. L'API répond (le load balancer peut mettre quelques minutes après le remplacement des pods)
sante = {}
for essai in range(30):
    try:
        statut, sante = appel("/health")
        if statut == 200:
            break
    except OSError:
        pass
    time.sleep(10)
verifie(sante.get("status") == "ok", "/health répond « ok »")
verifie(set(sante) == {"status"}, "/health ne révèle rien d'autre (ni version, ni détail)")

# 2. Version du modèle (route réservée à la clé). Pendant le remplacement progressif des pods, anciens et nouveaux
# répondent tour à tour : on attend que tous annoncent la même version (6 réponses consécutives identiques).
versions = set()
for essai in range(30):
    versions = set()
    for _ in range(6):
        try:
            versions.add(appel("/version")[1].get("model_version", ""))
        except OSError:
            versions.add("")
    if len(versions) == 1:
        break
    time.sleep(10)
verifie(len(versions) == 1, f"tous les pods annoncent la même version du modèle ({', '.join(sorted(versions))})")
version = next(iter(versions)) if len(versions) == 1 else ""
verifie(bool(version) and not version.startswith("dummy"), f"modèle réel (model_version = « {version} », pas « dummy-… »)")

# 3. Le modèle sépare un texte toxique d'un texte neutre (un modèle factice donne des scores fixes). La réponse ne
# contient que le score arrondi à la dizaine et le verdict (défense contre l'extraction du modèle).
_, toxique = appel("/score", {"text": "You are a stupid idiot"})
_, neutre = appel("/score", {"text": "Thanks for fixing the references, great work."})
verifie(toxique.get("toxique") is True and toxique.get("score", 0) >= 90, f"texte toxique : {toxique} (attendu : toxique, score >= 90)")
verifie(neutre.get("toxique") is False and neutre.get("score", 100) <= 30, f"texte neutre : {neutre} (attendu : non toxique, score <= 30)")
verifie(set(toxique) == {"score", "toxique"} and toxique.get("score", 1) % 10 == 0, "la réponse ne contient que score (arrondi à la dizaine) et toxique")

# 4. Authentification et surface exposée
verifie(appel("/score", {"text": "hi"}, cle=None)[0] == 401, "/score sans clé : 401")
verifie(appel("/score", {"text": "hi"}, cle="mauvaise")[0] == 401, "/score avec une mauvaise clé : 401")
verifie(appel("/version", cle=None)[0] == 401, "/version sans clé : 401")
verifie(appel("/docs", cle=None)[0] == 404, "documentation /docs fermée en production (404)")

sys.exit(1 if echecs else 0)
