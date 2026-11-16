"""Résume les journaux du load balancer (Cloud Logging) pour repérer et décrire une attaque.

    python supervision/analyser_journaux.py --projet <projet> [--heures 6] [--max 20000] [--ips]

Complète Grafana : Grafana dit QUAND et SUR QUELLE ROUTE ; ce script dit QUI (client pseudonymisé), COMMENT (user-agent,
chemins), et sépare 401 / 404 / 422 que Prometheus regroupe en « 4xx ». Lecture seule (commande `gcloud logging read`).

RGPD : les adresses IP sont des données personnelles. Par défaut elles sont remplacées par un identifiant court
(C1, C2…, établi par volume décroissant) : le résumé peut être collé dans INCIDENTS.md sans les révéler. `--ips` les
affiche en clair pour un usage immédiat (ne pas les écrire dans le dépôt, qui est public).
Les journaux du load balancer sont conservés 30 jours (voir le registre RGPD).
"""
import argparse
import collections
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

SONDES = re.compile(r"(xmlrpc|phpinfo|wp-|\.php|\.env|\.git|server-status|/stats|admin|passwd|/etc/|cgi-bin|actuator|\.\./)", re.I)

parser = argparse.ArgumentParser()
parser.add_argument("--projet", required=True)
parser.add_argument("--heures", type=float, default=6)
parser.add_argument("--max", type=int, default=20000, help="nombre maximal d'entrées lues")
parser.add_argument("--ips", action="store_true", help="afficher les adresses IP en clair")
args = parser.parse_args()

debut = (datetime.now(timezone.utc) - timedelta(hours=args.heures)).strftime("%Y-%m-%dT%H:%M:%SZ")
filtre = f'resource.type="http_load_balancer" AND timestamp>="{debut}"'
sortie = subprocess.run(["gcloud", "logging", "read", filtre, "--project", args.projet, "--limit", str(args.max),
                         "--format", "json"], capture_output=True, text=True)
if sortie.returncode:
    sys.exit("gcloud a échoué : " + sortie.stderr.strip()[:300])
entrees = [e["httpRequest"] | {"ts": e["timestamp"]} for e in json.loads(sortie.stdout or "[]") if "httpRequest" in e]
if not entrees:
    sys.exit("Aucune entrée sur la période.")
if len(entrees) >= args.max:
    print(f"ATTENTION : limite de {args.max} entrées atteinte, le début de la période est tronqué (augmenter --max).\n")


def chemin(url):
    m = re.match(r"https?://[^/]+(/[^?]*)", url or "")
    return m.group(1) if m else (url or "?")


def latence(e):
    try:
        return float(e.get("latency", "0s").rstrip("s"))
    except ValueError:
        return 0.0


clients = collections.Counter(e.get("remoteIp", "?") for e in entrees)
nom = {ip: (ip if args.ips else f"C{i + 1}") for i, (ip, _) in enumerate(clients.most_common())}
heures = sorted(e["ts"] for e in entrees)
print(f"Période lue : {heures[0][:19]} à {heures[-1][:19]} UTC — {len(entrees)} requêtes, {len(clients)} clients distincts\n")

print("== Statut / méthode / chemin")
for (st, me, ch), n in collections.Counter((e.get("status"), e.get("requestMethod"), chemin(e.get("requestUrl")))
                                           for e in entrees).most_common(12):
    print(f"  {n:6d}  {st}  {(me or '-'):5s} {(ch or '(requête mal formée)')[:60]}")

print("\n== Clients (volume, route principale, user-agent, statuts)")
for ip, n in clients.most_common(8):
    es = [e for e in entrees if e.get("remoteIp") == ip]
    ch = collections.Counter(chemin(e.get("requestUrl")) for e in es).most_common(1)[0]
    ua = collections.Counter((e.get("userAgent") or "")[:28] for e in es).most_common(1)[0][0]
    st = dict(collections.Counter(str(e.get("status")) for e in es))
    print(f"  {nom[ip]:>16s}  {n:6d} req   {ch[0][:24]:24s} {ua:28s} {st}")

print("\n== Minutes les plus chargées par client (rafales)")
for ip, _ in clients.most_common(4):
    par_min = collections.Counter(e["ts"][11:16] for e in entrees if e.get("remoteIp") == ip)
    pic = par_min.most_common(1)[0]
    if pic[1] >= 60:
        print(f"  {nom[ip]:>16s}  {pic[0]} UTC : {pic[1]} requêtes ({pic[1] / 60:.0f}/s)")

sonde = [e for e in entrees if SONDES.search(chemin(e.get("requestUrl")))]
print(f"\n== Chemins typiques de scanner ({len(sonde)} requêtes)")
for ch, n in collections.Counter(chemin(e.get("requestUrl"))[:50] for e in sonde).most_common(8):
    print(f"  {n:5d}  {ch}")

refus = [e for e in entrees if e.get("status") in (401, 403, 422)]
print(f"\n== Refus d'authentification et de validation ({len(refus)})")
for (st, ip), n in collections.Counter((e.get("status"), e.get("remoteIp")) for e in refus).most_common(6):
    print(f"  {n:5d}  code {st}  client {nom[ip]}")

lat = sorted(latence(e) for e in entrees if "/score" in (e.get("requestUrl") or "") and e.get("status") == 200)
if lat:
    print(f"\n== /score (réussites) : {len(lat)} requêtes, médiane {1000 * lat[len(lat) // 2]:.0f} ms, "
          f"P95 {1000 * lat[int(len(lat) * 0.95) - 1]:.0f} ms, max {1000 * lat[-1]:.0f} ms")
erreurs = collections.Counter(e.get("status") for e in entrees if (e.get("status") or 0) >= 500)
print("== Erreurs serveur (5xx) :", dict(erreurs) if erreurs else "aucune")
