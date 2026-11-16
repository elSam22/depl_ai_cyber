"""Serveur local du dashboard d'attaque (TP2). Sert la page et diffuse en streaming (SSE)
les résultats des attaques, lancées par le réseau contre l'API d'une équipe adverse — au choix,
sélectionnée dans le dashboard.

Les adresses et les clés ne sont JAMAIS écrites dans ce fichier : elles viennent de variables
d'environnement, pour ne jamais finir committées.

Lancement (depuis la racine), avec les deux groupes configurés :
    export URL_FLORENTIN=http://<adresse-florentin-gilane>
    export KEY_FLORENTIN=<leur-clé-api>
    export URL_AUREL=https://<adresse-aurel-baunell>
    export KEY_AUREL=<leur-clé-api>
    .venv/bin/uvicorn attack.serveur:app --port 8050
Puis ouvrir http://127.0.0.1:8050/

Si l'API d'un groupe présente un certificat HTTPS qui ne passe pas la vérification standard,
ne pas désactiver cette vérification sans y avoir réfléchi : VERIFIER_TLS_AUREL=0 le permet,
mais c'est un choix explicite à faire soi-même, après avoir compris pourquoi le certificat
échoue (domaine non reconnu, certificat auto-signé...), pas un réflexe pour faire taire l'erreur.
"""
import json
import os
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse

RACINE = Path(__file__).resolve().parent.parent
PAGE = Path(__file__).resolve().parent / "dashboard.html"
PHRASES = Path(__file__).resolve().parent / "phrases.csv"


def _bool_env(nom: str, defaut: bool = True) -> bool:
    return os.environ.get(nom, "1" if defaut else "0") not in ("0", "false", "False", "")


# Groupes adverses configurés. URL_FLORENTIN/KEY_FLORENTIN retombent sur URL/KEY pour rester
# compatibles avec les lancements précédents qui n'utilisaient qu'un seul groupe.
GROUPES = {
    "florentin_gilane": {
        "nom": "Florentin & Gilane",
        "url": os.environ.get("URL_FLORENTIN", os.environ.get("URL", "")).rstrip("/"),
        "key": os.environ.get("KEY_FLORENTIN", os.environ.get("KEY", "")),
        "verifier_tls": _bool_env("VERIFIER_TLS_FLORENTIN", True),
    },
    "aurel_baunell": {
        "nom": "Aurel & Baunell",
        "url": os.environ.get("URL_AUREL", "").rstrip("/"),
        "key": os.environ.get("KEY_AUREL", ""),
        "verifier_tls": _bool_env("VERIFIER_TLS_AUREL", True),
    },
    "exauce_gilbert": {
        "nom": "Exauce & Gilbert",
        "url": os.environ.get("URL_EXAUCE", "").rstrip("/"),
        "key": os.environ.get("KEY_EXAUCE", ""),
        "verifier_tls": _bool_env("VERIFIER_TLS_EXAUCE", True),
    },
}
GROUPE_PAR_DEFAUT = "florentin_gilane"


def _cible(groupe: str):
    """Renvoie le dict {nom, url, key, verifier_tls} du groupe, ou None si inconnu."""
    return GROUPES.get(groupe)


# Plafonds durs : même si le champ du front est modifié ou trafiqué, on ne dépasse jamais
# ces valeurs. Le test de charge vise des API qui ne nous appartiennent pas : les bornes
# doivent rester celles négociées avec chaque équipe, pas un choix laissé au navigateur.
# 2000 utilisateurs : chiffre validé avec les trois groupes (2026-11-13).
MAX_UTILISATEURS = 2000
MAX_DUREE_S = 600

# Budget de requêtes pour les attaques itératives (recherche de synonymes, mutation aléatoire) :
# nombre maximal d'appels à LEUR API par commentaire toxique. Avec 15 commentaires toxiques
# dans phrases.csv, ça fait au plus 15 x BUDGET_RECHERCHE requêtes par lancement de ces attaques.
BUDGET_RECHERCHE = 15

HOMOGLYPHES = {"a": "а", "e": "е", "o": "о", "i": "і", "c": "с", "p": "р", "y": "у", "x": "х"}
LEET = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "$", "t": "7"}
ZW = "​"
PONCTUATION = ",.!?;:'\""

# Synonymes connus pour les mots des commentaires toxiques de phrases.csv. Les mots absents
# de ce dictionnaire retombent sur des variantes de fautes de frappe (voir `_variantes_typo`).
SYNONYMES = {
    "stupid": "foolish", "idiot": "fool", "moron": "dolt", "worthless": "useless",
    "loser": "failure", "disgusting": "revolting", "garbage": "trash",
    "brainless": "mindless", "fools": "simpletons", "fail": "falter",
    "useless": "pointless", "clown": "jester", "dumb": "slow",
    "insufferable": "unbearable", "joke": "farce", "pathetic": "sad",
    "freak": "weirdo", "hate": "despise", "destroy": "ruin", "ugly": "hideous",
    "miserably": "badly", "complete": "total", "nobody": "no one",
}


def piéger(texte: str, rng) -> str:
    """Attaque 1 — Déguisement combiné (leet + homoglyphes + caractères invisibles) sur les mots longs."""
    t = "".join(LEET.get(c.lower(), c) if c.lower() in LEET and rng.random() < 0.4 else c for c in texte)
    t = "".join(HOMOGLYPHES.get(c.lower(), c) if c.lower() in HOMOGLYPHES and rng.random() < 0.7 else c for c in t)
    return " ".join(ZW.join(m) if len(m) > 3 else m for m in t.split())


def noyer(texte: str, textes_sains: list[str], cible_car: int = 4000) -> str:
    """Attaque 2 — Noyage : place le commentaire toxique après un pavé de texte neutre assez long
    pour sortir de la fenêtre de contexte d'un modèle transformer (qui tronque au-delà d'une limite
    fixe de tokens). Une seule requête, aucune itération."""
    pave, total, i = [], 0, 0
    while total < cible_car:
        s = textes_sains[i % len(textes_sains)]
        pave.append(s)
        total += len(s) + 1
        i += 1
    return " ".join(pave) + " " + texte


def _variantes_typo(mot_propre: str) -> list[str]:
    """3 fautes de frappe plausibles : lettre supprimée, deux lettres interverties, lettre doublée."""
    if len(mot_propre) <= 3:
        return []
    i = len(mot_propre) // 2
    inter = list(mot_propre)
    inter[i], inter[i + 1] = inter[i + 1], inter[i]
    return [mot_propre[:i] + mot_propre[i + 1:], "".join(inter), mot_propre[0] * 2 + mot_propre[1:]]


def _candidats(mot: str) -> list[str]:
    """Synonyme connu + variantes de fautes de frappe pour un mot (sans sa ponctuation)."""
    propre = mot.strip(PONCTUATION)
    base = propre.lower()
    out = [SYNONYMES[base]] if base in SYNONYMES else []
    out += _variantes_typo(propre)
    return out[:3]


def verdict(texte: str, session: requests.Session, cible: dict):
    """Interroge l'API du groupe `cible` : renvoie (score 0-100 ou None, détecté: bool|None,
    latence ms, erreur: str|None)."""
    headers = {"Content-Type": "application/json", "X-API-Key": cible["key"]}
    t0 = time.perf_counter()
    try:
        r = session.post(f"{cible['url']}/score", json={"text": texte}, headers=headers,
                         timeout=15, verify=cible.get("verifier_tls", True))
        latence = round(1000 * (time.perf_counter() - t0), 1)
        if r.status_code != 200:
            return None, None, latence, f"HTTP {r.status_code}"
        data = r.json()
        score = data.get("score")
        # Les groupes ne renvoient pas tous le même format : "label" (toxic/non_toxic),
        # "toxique" (booléen), ou seulement un "score" sans verdict explicite — dans ce
        # dernier cas, on retombe sur le même seuil que celui qu'on utilise nous-mêmes (50).
        if "label" in data:
            detecte = data["label"] == "toxic"
        elif "toxique" in data:
            detecte = bool(data["toxique"])
        elif score is not None:
            detecte = score >= 50
        else:
            detecte = None
        return score, detecte, latence, None
    except requests.exceptions.SSLError:
        return None, None, round(1000 * (time.perf_counter() - t0), 1), "certificat TLS invalide"
    except requests.RequestException as e:
        return None, None, round(1000 * (time.perf_counter() - t0), 1), str(e)[:80]


def recherche_synonymes(texte: str, session: requests.Session, cible: dict, budget: int = BUDGET_RECHERCHE):
    """Attaque 3 — Recherche gloutonne : essaie mot par mot un synonyme ou une faute de frappe,
    garde la substitution si elle fait baisser le score, s'arrête dès l'évasion ou le budget épuisé.
    Renvoie (texte final, score, détecté, erreur, requêtes consommées)."""
    score, detecte, _, erreur = verdict(texte, session, cible)
    requetes = 1
    mots = texte.split()
    for idx, mot in enumerate(mots):
        if requetes >= budget or detecte is False:
            break
        for cand in _candidats(mot):
            if requetes >= budget:
                break
            essai_mots = mots.copy()
            essai_mots[idx] = cand
            essai = " ".join(essai_mots)
            s, d, _, e = verdict(essai, session, cible)
            requetes += 1
            if s is not None and (score is None or s < score):
                score, detecte, erreur, mots = s, d, e, essai_mots
            if detecte is False:
                break
    return " ".join(mots), score, detecte, erreur, requetes


def mutation_aleatoire(texte: str, session: requests.Session, cible: dict, budget: int = BUDGET_RECHERCHE):
    """Attaque 4 — Escalade aléatoire : modifie un caractère au hasard dans un mot long, garde la
    mutation si le score baisse, recommence depuis la meilleure version trouvée. Renvoie
    (texte final, score, détecté, erreur, requêtes consommées)."""
    import random
    rng = random.Random()
    score, detecte, _, erreur = verdict(texte, session, cible)
    requetes = 1
    mots = texte.split()
    idx_valides = [i for i, m in enumerate(mots) if len(m.strip(PONCTUATION)) > 3]
    if not idx_valides:
        return texte, score, detecte, erreur, requetes
    while requetes < budget and detecte is not False:
        i = rng.choice(idx_valides)
        mot = mots[i]
        pos = rng.randrange(len(mot))
        c = mot[pos].lower()
        if c in LEET and rng.random() < 0.5:
            nouveau = mot[:pos] + LEET[c] + mot[pos + 1:]
        elif c in HOMOGLYPHES:
            nouveau = mot[:pos] + HOMOGLYPHES[c] + mot[pos + 1:]
        else:
            nouveau = mot[:pos] + ZW + mot[pos:]
        essai_mots = mots.copy()
        essai_mots[i] = nouveau
        essai = " ".join(essai_mots)
        s, d, _, e = verdict(essai, session, cible)
        requetes += 1
        if s is not None and s < score:
            score, detecte, erreur, mots = s, d, e, essai_mots
    return " ".join(mots), score, detecte, erreur, requetes


app = FastAPI(title="Dashboard attaque (équipe adverse)")


@app.get("/")
def accueil():
    return FileResponse(PAGE)


@app.get("/groupes")
def groupes():
    """Liste les groupes adverses connus et s'ils sont configurés (URL + clé présentes).
    Ne renvoie jamais la clé elle-même."""
    return {
        id_: {"nom": g["nom"], "url": g["url"], "configure": bool(g["url"] and g["key"])}
        for id_, g in GROUPES.items()
    }


def flux_generique(nom_attaque: str, attaquer_fn, cible: dict):
    """Génère un événement SSE par phrase, avec le résultat avant/après, contre l'API distante.

    `attaquer_fn(texte, session, cible)` renvoie (texte_piege, score_apres, detecte_apres, erreur_apres) ;
    elle peut faire une seule requête (déguisement, noyage) ou plusieurs (recherche, mutation)."""
    if not cible or not cible["url"] or not cible["key"]:
        yield f"event: erreur\ndata: {json.dumps({'message': 'Groupe non configuré : URL ou clé manquante côté serveur.'})}\n\n"
        return

    df = pd.read_csv(PHRASES)
    total_tox = int((df.toxic == 1).sum())
    debut = {"total": len(df), "toxiques": total_tox, "cible": cible["url"],
             "groupe": cible["nom"], "attaque": nom_attaque}
    yield f"event: debut\ndata: {json.dumps(debut)}\n\n"

    detect_avant = detect_apres = evasions = 0
    latences = []
    with requests.Session() as session:
        for i, r in df.iterrows():
            t0 = time.perf_counter()
            so, do, lo, erro = verdict(r.text, session, cible)
            if r.toxic == 1:
                piege, sp, dp, errp = attaquer_fn(r.text, session, cible)
            else:
                piege, sp, dp, errp = r.text, so, do, erro
            latences.append(round(1000 * (time.perf_counter() - t0), 1))
            if r.toxic == 1 and do is not None and dp is not None:
                detect_avant += int(do)
                detect_apres += int(dp)
                if do and not dp:
                    evasions += 1
            # Ce qui est affiché = exactement ce qui est envoyé sur le réseau à leur API.
            ligne = {
                "i": int(i), "texte": r.text, "toxique_reel": int(r.toxic),
                "score_avant": so, "detecte_avant": do, "erreur_avant": erro,
                "piege": piege, "score_apres": sp, "detecte_apres": dp, "erreur_apres": errp,
                "evasion": bool(r.toxic == 1 and do and dp is False),
                "rappel_avant": round(detect_avant / total_tox, 3) if total_tox else 0,
                "rappel_apres": round(detect_apres / total_tox, 3) if total_tox else 0,
                "evasions": evasions,
                "latence_moyenne": round(float(np.mean(latences)), 1),
            }
            yield f"event: phrase\ndata: {json.dumps(ligne, ensure_ascii=False)}\n\n"

    yield f"event: fin\ndata: {json.dumps({'evasions': evasions, 'toxiques': total_tox})}\n\n"


def _attaque_deguisement(texte, session, cible):
    import random
    piege = piéger(texte, random.Random(42))
    s, d, _, e = verdict(piege, session, cible)
    return piege, s, d, e


def _attaque_noyage(texte, session, cible):
    sains = pd.read_csv(PHRASES).query("toxic == 0").text.tolist()
    piege = noyer(texte, sains)
    s, d, _, e = verdict(piege, session, cible)
    return piege, s, d, e


def _attaque_synonymes(texte, session, cible):
    piege, s, d, e, _ = recherche_synonymes(texte, session, cible)
    return piege, s, d, e


def _attaque_mutation(texte, session, cible):
    piege, s, d, e, _ = mutation_aleatoire(texte, session, cible)
    return piege, s, d, e


ATTAQUES_DISPONIBLES = {
    "deguisement": ("Déguisement (leet/homoglyphes)", _attaque_deguisement),
    "noyage": ("Noyage (troncature)", _attaque_noyage),
    "synonymes": ("Recherche de synonymes", _attaque_synonymes),
    "mutation": ("Mutation aléatoire", _attaque_mutation),
}


@app.get("/lancer/{type_attaque}")
def lancer(type_attaque: str, groupe: str = GROUPE_PAR_DEFAUT):
    if type_attaque not in ATTAQUES_DISPONIBLES:
        return {"erreur": f"type d'attaque inconnu : {type_attaque}"}
    cible = _cible(groupe)
    if cible is None:
        return {"erreur": f"groupe inconnu : {groupe}"}
    _, fn = ATTAQUES_DISPONIBLES[type_attaque]
    return StreamingResponse(flux_generique(type_attaque, fn, cible), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ----------------------- Test de charge (validé au préalable avec l'équipe adverse) -----------------------

ARRET_CHARGE = threading.Event()   # un seul test de charge actif à la fois ; /charge/stop l'interrompt


def _utilisateur_charge(textes, session, cible, stats, verrou, stop_event):
    """Un utilisateur simulé : boucle de requêtes avec pause 0,5-1 s (même rythme que le TP1)."""
    import random
    rng = random.Random()
    i = 0
    while not stop_event.is_set():
        texte = textes[i % len(textes)]
        i += 1
        _, _, latence, erreur = verdict(texte, session, cible)
        with verrou:
            stats["envoyees"] += 1
            stats["latences"].append(latence)
            if erreur:
                stats["erreurs"] += 1
        stop_event.wait(rng.uniform(0.5, 1.0))


def flux_charge(utilisateurs: int, duree_s: int, cible: dict):
    """Lance `utilisateurs` threads pendant `duree_s` secondes et diffuse un instantané par seconde."""
    if not cible or not cible["url"] or not cible["key"]:
        yield f"event: erreur\ndata: {json.dumps({'message': 'Groupe non configuré : URL ou clé manquante côté serveur.'})}\n\n"
        return

    utilisateurs = max(1, min(int(utilisateurs), MAX_UTILISATEURS))
    duree_s = max(5, min(int(duree_s), MAX_DUREE_S))
    textes = pd.read_csv(PHRASES).text.tolist()

    ARRET_CHARGE.clear()
    yield f"event: debut\ndata: {json.dumps({'utilisateurs': utilisateurs, 'duree': duree_s, 'cible': cible['url'], 'groupe': cible['nom']})}\n\n"

    stats = {"envoyees": 0, "erreurs": 0, "latences": []}
    verrou = threading.Lock()
    session = requests.Session()
    threads = [threading.Thread(target=_utilisateur_charge, args=(textes, session, cible, stats, verrou, ARRET_CHARGE), daemon=True)
               for _ in range(utilisateurs)]
    for t in threads:
        t.start()

    t0 = time.monotonic()
    envoyees_avant = 0
    arretee = False
    try:
        while time.monotonic() - t0 < duree_s:
            if ARRET_CHARGE.wait(timeout=1.0):   # True dès que /charge/stop est appelé, sans attendre la seconde pleine
                arretee = True
                break
            with verrou:
                envoyees, erreurs = stats["envoyees"], stats["erreurs"]
                lat = list(stats["latences"][-200:])   # fenêtre récente pour la latence affichée
            ecoule = round(time.monotonic() - t0, 1)
            tick = {
                "ecoule": ecoule, "duree": duree_s,
                "envoyees": envoyees, "erreurs": erreurs,
                "reqs_par_s": envoyees - envoyees_avant,
                "taux_erreur": round(erreurs / envoyees, 3) if envoyees else 0,
                "latence_moyenne": round(float(np.mean(lat)), 1) if lat else 0,
                "latence_p95": round(float(np.percentile(lat, 95)), 1) if lat else 0,
            }
            envoyees_avant = envoyees
            yield f"event: tick\ndata: {json.dumps(tick)}\n\n"
    finally:
        ARRET_CHARGE.set()
        for t in threads:
            t.join(timeout=3)
        session.close()

    with verrou:
        envoyees, erreurs, lat = stats["envoyees"], stats["erreurs"], stats["latences"]
    resume = {"envoyees": envoyees, "erreurs": erreurs, "duree": duree_s, "arretee": arretee,
              "latence_p95": round(float(np.percentile(lat, 95)), 1) if lat else 0}
    yield f"event: fin\ndata: {json.dumps(resume)}\n\n"


@app.get("/charge")
def charge(utilisateurs: int = 10, duree: int = 60, groupe: str = GROUPE_PAR_DEFAUT):
    cible = _cible(groupe)
    return StreamingResponse(flux_charge(utilisateurs, duree, cible), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/charge/stop")
def charge_stop():
    """Arrête immédiatement le test de charge en cours (les threads s'arrêtent entre deux requêtes)."""
    ARRET_CHARGE.set()
    return {"ok": True}
