"""Outils communs du Red Team interne : cible, clé, requêtes, écriture des résultats, Prometheus, Kubernetes.

La cible et la clé viennent de l'environnement (URL, API_KEY) et ne sont JAMAIS écrites : le dépôt est public.
Avant d'écrire un résultat, l'adresse de l'API (nom et IP) est remplacée par « <cible> ».
"""
import functools
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

DOSSIER = Path(__file__).resolve().parent
RACINE = DOSSIER.parent
RESULTATS = DOSSIER / "resultats"
URL = os.environ.get("URL", "").rstrip("/")
CLE = os.environ.get("API_KEY", "")
HOTE = URL.split("//", 1)[-1] if URL else ""
AGENT = "redteam-interne-dss/1.0"      # signature des requêtes : on les reconnaît dans les journaux
# Lancé par l'interface (interface/serveur.py) : chaque mesure est aussi publiée en direct sur la sortie standard
FLUX = os.environ.get("REDTEAM_FLUX") == "1"


def verifier_cible() -> None:
    """Refuse de tirer sans cible HTTPS ni clé (garde-fou contre une faute de frappe)."""
    if not URL.startswith("https://") or not CLE:
        sys.exit("Définir URL=https://<adresse de NOTRE API> et API_KEY (voir RedTeamIA/README.md).")


@functools.lru_cache(maxsize=1)
def ip_cible() -> str:
    try:
        return socket.gethostbyname(HOTE)
    except OSError:
        return ""


def client(timeout: float = 20) -> httpx.Client:
    """Client HTTP sans suivi des redirections (on veut voir les 301) et avec notre signature."""
    return httpx.Client(base_url=URL, timeout=timeout, follow_redirects=False, headers={"User-Agent": AGENT})


def masquer(texte: str) -> str:
    """Retire l'adresse de l'API d'un texte avant de l'écrire dans le dépôt public."""
    for secret in (URL, HOTE, ip_cible(), CLE):
        if secret:
            texte = texte.replace(secret, "<cible>" if secret != CLE else "<clé>")
    return texte


def evenement(type_: str, **donnees) -> None:
    """Publie une mesure pour le tableau de bord (ligne « @@EVT {json} »), adresse masquée. Sans interface : rien."""
    if FLUX:
        ligne = json.dumps({"type": type_, "t": round(time.time(), 2), **donnees}, ensure_ascii=False)
        print("@@EVT " + masquer(ligne), flush=True)


def ecrire(nom: str, donnees: dict) -> Path:
    """Écrit resultats/<nom>.json (horodaté, adresse masquée)."""
    RESULTATS.mkdir(exist_ok=True)
    donnees = {"vague": nom, "date_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), **donnees}
    chemin = RESULTATS / f"{nom}.json"
    chemin.write_text(masquer(json.dumps(donnees, ensure_ascii=False, indent=1)), encoding="utf-8")
    print(f"-> {chemin.relative_to(RACINE)}")
    return chemin


def percentile(valeurs: list[float], q: float) -> float | None:
    """Percentile simple (rang le plus proche) : suffisant pour des P50/P95 de mesure."""
    if not valeurs:
        return None
    v = sorted(valeurs)
    return v[min(len(v) - 1, max(0, round(q / 100 * len(v)) - 1))]


def kubectl(*args: str, entree: str | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["kubectl", *args], input=entree, capture_output=True, text=True, timeout=timeout)


def prometheus(api: str, **params) -> dict:
    """Interroge Prometheus (lecture seule) par le proxy du serveur Kubernetes : pas de port à ouvrir."""
    chemin = (f"/api/v1/namespaces/monitoring/services/monitoring-kube-prometheus-prometheus:9090/proxy/api/v1/{api}"
              f"?{urlencode(params)}")
    r = kubectl("get", "--raw", chemin, timeout=30)
    return json.loads(r.stdout) if r.returncode == 0 else {"erreur": r.stderr.strip()[:200]}


def etat_api() -> dict:
    """Pods de l'API : nombre prêts, redémarrages cumulés, réplicas voulus par l'autoscaler."""
    r = kubectl("get", "pods", "-l", "app=dss-api", "-o", "json")
    pods = json.loads(r.stdout)["items"] if r.returncode == 0 else []
    prets = sum(1 for p in pods if all(c.get("ready") for c in p["status"].get("containerStatuses", [{}])))
    redem = sum(c.get("restartCount", 0) for p in pods for c in p["status"].get("containerStatuses", []))
    hpa = kubectl("get", "hpa", "dss-api", "-o", "jsonpath={.status.desiredReplicas}").stdout.strip()
    return {"t": round(time.time()), "pods": len(pods), "prets": prets, "redemarrages": redem,
            "hpa_voulu": int(hpa) if hpa.isdigit() else None}


def attendre_si_refus(reponse: httpx.Response) -> bool:
    """429 ou 503 : attend le délai annoncé (Retry-After) et renvoie True pour que l'appelant réessaie."""
    if reponse.status_code in (429, 503):
        time.sleep(float(reponse.headers.get("retry-after", "2")) + 0.5)
        return True
    return False


def resume(nom: str) -> dict:
    """Ce que le tableau de bord affiche sur la carte de la vague, lu dans son fichier de résultats."""
    d = json.loads((RESULTATS / f"{nom}.json").read_text(encoding="utf-8"))
    r0 = {"date_utc": d.get("date_utc")}
    cles = ["verdict", "ecarts", "reponses_exploitables", "exploitables_par_min", "codes", "premier_429_apres_s",
            "evasion", "sondes_ratees", "total_requetes_attaque", "total_acceptees_200", "force_brute"]
    r = r0 | {k: d[k] for k in cles if k in d}
    if "sonde_legitime" in d:
        r["sonde_legitime"] = d["sonde_legitime"]
        r["alertes"] = d["supervision"]["alertes_declenchees_s_apres_debut"]
    return r
