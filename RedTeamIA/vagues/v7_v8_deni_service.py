"""Vagues 7 et 8 : déni de service, depuis une adresse (v7) puis depuis deux adresses (v8).

Reproduit le tir du professeur (« 43 685 requêtes ACCEPTÉES en 4 min, ~180 req/s, P95 4 276 ms contre 56 ms, ×76 »),
avec la clé valide (pire cas : le tir atteint le modèle), et mesure ce que subit un utilisateur LÉGITIME pendant ce temps.

- Sonde légitime : un pod du cluster appelle /score toutes les 2 s en passant par l'adresse PUBLIQUE (même chemin
  qu'un vrai client). Elle sort par l'adresse de son nœud, différente de celle de l'attaquant.
- v7 : attaquant = ce poste, 180 req/s, 128 requêtes simultanées, 120 s.
- v8 : deux attaquants en même temps (ce poste + un pod sur un AUTRE nœud que la sonde), 90 req/s chacun.
  Limite assumée : deux adresses seulement, ce n'est pas un vrai déni de service distribué.
- Garde-fous : ceux d'attaquant.py, plus l'arrêt immédiat si un pod de l'API redémarre.
- Supervision : on relève dans Prometheus les alertes déclenchées et les pics (débit, refus, latence, pods).

La clé n'est jamais écrite : les pods la lisent dans le Secret Kubernetes de l'API (secretKeyRef).
"""
import json
import subprocess
import sys
import threading
import time

from commun import DOSSIER, URL, ecrire, etat_api, evenement, kubectl, percentile, prometheus, verifier_cible

sys.path.insert(0, str(DOSSIER))
from attaquant import lancer  # noqa: E402

ESPACE = "default"
SONDE, ATTAQUANT, CONFIG = "redteam-sonde", "redteam-attaquant", "redteam-attaquant-script"
REFERENCE_S, RECUPERATION_S, TIR_S = 60, 60, 120
TEXTE_SONDE = "I really enjoyed this article, thank you"


def env_cible():
    return [{"name": "URL", "value": URL},
            {"name": "API_KEY", "valueFrom": {"secretKeyRef": {"name": "dss-api-key", "key": "API_KEY"}}}]


def manifeste_sonde() -> dict:
    script = ('while true; do t=$(date +%s); '
              'r=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" --max-time 30 -X POST "$URL/score" '
              '-H "Content-Type: application/json" -H "X-API-Key: $API_KEY" '
              f"-d '{{\"text\":\"{TEXTE_SONDE}\"}}'); echo \"$t $r\"; sleep 2; done")
    return {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": SONDE, "labels": {"app": SONDE}},
            "spec": {"restartPolicy": "Never", "containers": [{
                "name": "sonde", "image": "curlimages/curl:8.11.1", "command": ["sh", "-c", script], "env": env_cible(),
                "resources": {"requests": {"cpu": "250m", "memory": "256Mi"}, "limits": {"cpu": "250m", "memory": "256Mi"}}}]}}


def manifeste_attaquant(debit: float, concurrence: int) -> dict:
    commande = ["python", "/script/attaquant.py", "--debit", str(debit), "--concurrence", str(concurrence),
                "--duree", str(TIR_S), "--attendre-fichier", "/tmp/go", "--fichier-arret", "/tmp/stop", "--flux"]
    anti = {"podAntiAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": [{
        "labelSelector": {"matchLabels": {"app": SONDE}}, "topologyKey": "kubernetes.io/hostname"}]}}
    return {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": ATTAQUANT, "labels": {"app": ATTAQUANT}},
            "spec": {"restartPolicy": "Never", "affinity": anti, "containers": [{
                "name": "attaquant", "image": "python:3.12-slim", "command": commande, "env": env_cible(),
                "volumeMounts": [{"name": "script", "mountPath": "/script"}],
                "resources": {"requests": {"cpu": "1", "memory": "1Gi"}, "limits": {"cpu": "1", "memory": "1Gi"}}}],
                "volumes": [{"name": "script", "configMap": {"name": CONFIG}}]}}


def appliquer(manifeste: dict):
    r = kubectl("apply", "-f", "-", entree=json.dumps(manifeste))
    if r.returncode:
        sys.exit("kubectl apply : " + r.stderr[:300])


def attendre_pret(nom: str, delai_s: int = 600):
    r = kubectl("wait", "--for=condition=Ready", f"pod/{nom}", f"--timeout={delai_s}s", timeout=delai_s + 30)
    if r.returncode:
        raise RuntimeError(f"pod {nom} pas prêt : {r.stderr[:200]}")


def noeud(nom: str) -> str:
    return kubectl("get", "pod", nom, "-o", "jsonpath={.spec.nodeName}").stdout.strip()


def lire_sonde() -> list[tuple[int, int, float]]:
    """Journal de la sonde : (instant epoch, code HTTP, durée en s)."""
    lignes = []
    for l in kubectl("logs", SONDE).stdout.splitlines():
        p = l.split()
        if len(p) == 3 and p[0].isdigit() and p[1].isdigit():
            lignes.append((int(p[0]), int(p[1]), float(p[2])))
    return lignes


def stats_sonde(lignes, debut, fin) -> dict:
    sel = [(c, d) for t, c, d in lignes if debut <= t < fin]
    ok = [d * 1000 for c, d in sel if c == 200]
    return {"requetes": len(sel), "reussies": len(ok), "taux_succes": round(len(ok) / len(sel), 3) if sel else None,
            "codes": {str(c): sum(1 for x, _ in sel if x == c) for c in sorted({c for c, _ in sel})},
            "p50_ms": round(percentile(ok, 50)) if ok else None, "p95_ms": round(percentile(ok, 95)) if ok else None,
            "max_ms": round(max(ok)) if ok else None}


def suivre_journal(pod: str, traiter, fin: threading.Event):
    """Lit en continu le journal d'un pod (kubectl logs -f) et passe chaque ligne à `traiter` (tableau de bord)."""
    proc = subprocess.Popen(["kubectl", "logs", "-f", pod], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    def lire():
        for ligne in proc.stdout:
            traiter(ligne.strip())
    threading.Thread(target=lire, daemon=True).start()
    threading.Thread(target=lambda: (fin.wait(), proc.terminate()), daemon=True).start()


def ligne_sonde(ligne: str):
    p = ligne.split()
    if len(p) == 3 and p[0].isdigit() and p[1].isdigit():
        evenement("sonde", t_sonde=int(p[0]), code=int(p[1]), ms=round(float(p[2]) * 1000))


def ligne_attaquant_pod(ligne: str):
    if ligne.startswith("@@SEC "):
        evenement("charge", source="pod", **json.loads(ligne[6:]))


def veille_cluster(fin: threading.Event):
    """Pendant toute la vague : état des pods (10 s) et alertes Prometheus (15 s), pour le tableau de bord."""
    n = 0
    while not fin.is_set():
        evenement("pods", **etat_api())
        if n % 3 == 0:
            r = prometheus("query", query='ALERTS{alertname=~"Dss.*"}')
            evenement("alertes", liste=[{"nom": s["metric"]["alertname"], "etat": s["metric"]["alertstate"],
                                          "motif": s["metric"].get("motif")} for s in r.get("data", {}).get("result", [])])
        n += 1
        fin.wait(5)


def surveiller_pods(arret: threading.Event, releves: list, redem_initial: int):
    """Toutes les 10 s : état des pods. Un redémarrage = service cassé -> on coupe tout (kill switch)."""
    while not arret.is_set():
        e = etat_api()
        releves.append(e)
        if e["redemarrages"] > redem_initial:
            arret.set()
            releves.append({"t": e["t"], "kill_switch": "redémarrage d'un pod de l'API"})
            evenement("kill_switch", raison="redémarrage d'un pod de l'API")
        arret.wait(10)


def supervision(debut: int, fin: int) -> dict:
    """Ce que montrait la supervision pendant le tir : alertes déclenchées et pics des indicateurs."""
    pas = "15s"
    def pic(requete):
        r = prometheus("query_range", query=requete, start=debut, end=fin, step=pas)
        try:
            return {s["metric"].get("motif", s["metric"].get("alertname", "total")):
                    round(max(float(v[1]) for v in s["values"]), 2) for s in r["data"]["result"]}
        except (KeyError, ValueError):
            return {"erreur": str(r)[:150]}
    alertes = prometheus("query_range", query='ALERTS{alertname=~"Dss.*",alertstate="firing"}', start=debut,
                         end=fin + 300, step=pas)
    declenchees = {}
    for s in alertes.get("data", {}).get("result", []):
        premiere = min(float(v[0]) for v in s["values"])
        declenchees[s["metric"]["alertname"]] = round(premiere - debut)
    return {
        "alertes_declenchees_s_apres_debut": declenchees,
        "pic_requetes_par_s": pic('sum(rate(http_requests_total{namespace="default",pod=~"dss-api.*"}[1m]))'),
        "pic_refus_par_s_par_motif": pic('sum by (motif) (rate(dss_refus_total{namespace="default"}[1m]))'),
        "pic_p95_score_s": pic('histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket'
                               '{handler="/score",namespace="default"}[1m])))'),
        "pic_pods_prets": pic('kube_deployment_status_replicas_ready{deployment="dss-api",namespace="default"}'),
        "pic_cpu_coeurs": pic('sum(rate(container_cpu_usage_seconds_total{namespace="default",pod=~"dss-api.*",container!=""}[1m]))'),
    }


def tir(nom: str, sources: list[str], sonde_lignes_fn) -> dict:
    """Un tir complet : référence, attaque (une ou deux sources), récupération, puis mesures."""
    print(f"== {nom} : référence {REFERENCE_S} s (sonde seule)...", flush=True)
    evenement("phase", tir=nom, phase="référence", duree=REFERENCE_S)
    t_ref = int(time.time())
    time.sleep(REFERENCE_S)
    etat_avant = etat_api()
    arret, releves = threading.Event(), []
    garde = threading.Thread(target=surveiller_pods, args=(arret, releves, etat_avant["redemarrages"]), daemon=True)
    resultats = {}
    debit = 180 / len(sources)
    if "pod" in sources:
        kubectl("exec", ATTAQUANT, "--", "touch", "/tmp/go")          # le pod attaquant démarre
    t_debut = int(time.time())
    garde.start()
    print(f"== {nom} : tir {TIR_S} s, {len(sources)} source(s), {debit:.0f} req/s chacune...", flush=True)
    evenement("phase", tir=nom, phase="tir", duree=TIR_S, sources=sources, debit=debit)
    res_local = lancer(debit, 128 if len(sources) == 1 else 64, TIR_S, True, "/score", arret=arret,
                       chaque_seconde=lambda b: evenement("charge", source="poste", **b))
    if res_local["arret"].startswith("kill switch"):
        evenement("kill_switch", raison=res_local["arret"])
    t_fin = int(time.time())
    if "pod" in sources:
        kubectl("exec", ATTAQUANT, "--", "touch", "/tmp/stop")
        kubectl("wait", "--for=jsonpath={.status.phase}=Succeeded", f"pod/{ATTAQUANT}", "--timeout=120s", timeout=150)
        sortie = kubectl("logs", ATTAQUANT).stdout.strip().splitlines()
        resultats["attaquant_pod"] = json.loads(sortie[-1]) if sortie else {"erreur": "pas de sortie"}
    resultats["attaquant_poste"] = res_local
    print(f"== {nom} : récupération {RECUPERATION_S} s...", flush=True)
    evenement("phase", tir=nom, phase="récupération", duree=RECUPERATION_S)
    time.sleep(RECUPERATION_S)
    arret.set()
    t_recup = int(time.time())
    lignes = sonde_lignes_fn()
    ref, att, rec = (stats_sonde(lignes, t_ref, t_debut), stats_sonde(lignes, t_debut, t_fin),
                     stats_sonde(lignes, t_fin, t_recup))
    total = sum(r.get("requetes", 0) for k, r in resultats.items() if k.startswith("attaquant"))
    acceptees = sum(r.get("acceptees_200", 0) for k, r in resultats.items() if k.startswith("attaquant"))
    ratio = round(att["p95_ms"] / ref["p95_ms"], 1) if att.get("p95_ms") and ref.get("p95_ms") else None
    return {"sources": sources, "fenetres_epoch": {"reference": t_ref, "debut": t_debut, "fin": t_fin, "fin_recuperation": t_recup},
            "attaquants": resultats, "total_requetes_attaque": total, "total_acceptees_200": acceptees,
            "sonde_legitime": {"reference": ref, "pendant_attaque": att, "recuperation": rec,
                               "multiplicateur_p95": ratio},
            "pods": {"avant": etat_avant, "releves": releves, "apres": etat_api()},
            "supervision": supervision(t_debut, t_recup),
            "reference_professeur": {"acceptees": "43 685 en 4 min (~180 req/s)", "p95": "4 276 ms contre 56 ms (×76)",
                                     "erreurs": "0 %"}}


def nettoyer():
    for objet in (f"pod/{SONDE}", f"pod/{ATTAQUANT}", f"configmap/{CONFIG}"):
        kubectl("delete", objet, "--ignore-not-found", "--wait=false")


def main(phases=("v7", "v8")):
    verifier_cible()
    fin = threading.Event()
    try:
        nettoyer()
        time.sleep(5)
        appliquer(manifeste_sonde())
        evenement("phase", tir="préparation", phase="sonde légitime en démarrage")
        attendre_pret(SONDE)
        print(f"   sonde prête (nœud {noeud(SONDE)[-6:]})", flush=True)
        suivre_journal(SONDE, ligne_sonde, fin)
        threading.Thread(target=veille_cluster, args=(fin,), daemon=True).start()
        if "v7" in phases:
            ecrire("v7_deni_service", tir("v7", ["poste"], lire_sonde))
        if "v8" in phases:
            r = kubectl("create", "configmap", CONFIG, f"--from-file=attaquant.py={DOSSIER / 'attaquant.py'}")
            if r.returncode:
                sys.exit("configmap : " + r.stderr[:200])
            appliquer(manifeste_attaquant(90, 64))
            print("   pod attaquant en préparation (Autopilot peut ajouter un nœud : jusqu'à 10 min)...", flush=True)
            evenement("phase", tir="v8", phase="pod attaquant en préparation (jusqu'à 10 min)")
            attendre_pret(ATTAQUANT, 600)
            suivre_journal(ATTAQUANT, ligne_attaquant_pod, fin)
            n1, n2 = noeud(SONDE), noeud(ATTAQUANT)
            print(f"   attaquant prêt, nœud distinct de la sonde : {n1 != n2}", flush=True)
            res = tir("v8", ["poste", "pod"], lire_sonde)
            res["noeuds_distincts_sonde_attaquant"] = n1 != n2
            ecrire("v8_multi_adresses", res)
    finally:
        fin.set()
        evenement("phase", tir="fin", phase="nettoyage")
        nettoyer()
        print("   pods et configmap du Red Team supprimés", flush=True)


if __name__ == "__main__":
    main(tuple(sys.argv[1:]) or ("v7", "v8"))
