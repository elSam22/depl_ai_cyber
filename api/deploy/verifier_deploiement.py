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
        with urllib.request.urlopen(requete, timeout=30) as r:   # nosec B310 : schéma vérifié plus haut
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

# Pendant le remplacement progressif des pods, anciens et nouveaux répondent tour à tour : on attend que tous les pods
# annoncent la même version (6 réponses consécutives identiques) avant de juger.
versions = set()
for essai in range(30):
    versions = set()
    for _ in range(6):
        try:
            versions.add(appel("/health")[1].get("model_version", ""))
        except OSError:
            versions.add("")
    if len(versions) == 1:
        break
    time.sleep(10)
verifie(len(versions) == 1, f"tous les pods annoncent la même version du modèle ({', '.join(sorted(versions))})")
version = sante.get("model_version", "") if len(versions) != 1 else next(iter(versions))
verifie(bool(version) and not version.startswith("dummy"), f"modèle réel (model_version = « {version} », pas « dummy-… »)")

# 2. Le modèle sépare un texte toxique d'un texte neutre (un modèle factice donne des scores fixes)
_, toxique = appel("/score", {"text": "You are a stupid idiot"})
_, neutre = appel("/score", {"text": "Thanks for fixing the references, great work."})
p_t, p_n = toxique.get("labels", {}).get("toxic", -1), neutre.get("labels", {}).get("toxic", -1)
verifie(p_t > 0.9 and p_n < 0.3, f"probabilité « toxic » : {p_t} (texte toxique, attendu > 0,9) contre {p_n} (texte neutre, attendu < 0,3)")
verifie(toxique.get("model_version") == version, "/score et /health annoncent la même version du modèle")

# 3. L'authentification est en place
verifie(appel("/score", {"text": "hi"}, cle=None)[0] == 401, "sans clé : 401")
verifie(appel("/score", {"text": "hi"}, cle="mauvaise")[0] == 401, "mauvaise clé : 401")

sys.exit(1 if echecs else 0)
