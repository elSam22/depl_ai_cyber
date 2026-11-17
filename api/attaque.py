"""Red team : simule contre NOTRE API déployée les attaques du TP sécurité, pour remplir
la grille (S7, S8) et prouver que les défenses tiennent. Mesure ce qui arrive à l'API
pendant chaque scénario : codes retour, latence, part de requêtes bloquées (429).

À n'utiliser QUE contre une API dont on est responsable (la nôtre) ou qu'on est
explicitement autorisé à tester. Cible via la variable d'environnement URL.

Usage :
    URL=https://<domaine>.sslip.io python securite/attaque_resilience.py

"""
import argparse
import asyncio
import os
import time
from collections import Counter

import aiohttp

URL = os.environ.get("URL", "http://localhost:8080").rstrip("/")
KEY = os.environ.get("KEY", "")
TEXTE = {"text": "You are a stupid idiot, go away"}


async def un_appel(session, headers, payload, stats, latences):
    t0 = time.perf_counter()
    try:
        async with session.post(f"{URL}/score", json=payload, headers=headers) as r:
            await r.read()
            stats[r.status] += 1
    except asyncio.TimeoutError:
        stats["timeout"] += 1
    except aiohttp.ClientError:
        stats["connexion_refusee"] += 1
    latences.append((time.perf_counter() - t0) * 1000)


async def travailleur(session, headers, payload, fin, stats, latences):
    while time.monotonic() < fin:
        await un_appel(session, headers, payload, stats, latences)


async def scenario(nom, headers, payload, users, duree):
    stats, latences = Counter(), []
    fin = time.monotonic() + duree
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        taches = [travailleur(session, headers, payload, fin, stats, latences) for _ in range(users)]
        await asyncio.gather(*taches)

    total = sum(stats.values())
    latences.sort()
    p95 = latences[int(len(latences) * 0.95)] if latences else 0
    print(f"\n=== {nom}  ({users} clients en parallèle, {duree} s)")
    print(f"  requêtes envoyées : {total}  (~{total / duree:.0f}/s)")
    for code, n in sorted(stats.items(), key=lambda x: str(x[0])):
        print(f"  {str(code):>16} : {n:5}  ({100 * n / total:.1f} %)")
    print(f"  latence médiane : {latences[len(latences)//2]:.0f} ms | P95 : {p95:.0f} ms")
    bloquees = stats.get(429, 0)
    cinq_xx = sum(n for c, n in stats.items() if isinstance(c, int) and c >= 500)
    verdict = ("DÉFENSE OK : l'excédent est refusé proprement (429)" if bloquees
               else "PAS DE LIMITE : toutes les requêtes passent, risque de saturation" if not cinq_xx
               else "SATURATION : des 5xx apparaissent, l'API souffre")
    print(f"  -> {verdict}")


SCENARIOS = {
    # S8 : rafale SANS clé -> doit rester 401, le service ne doit pas tomber
    "flood-sans-cle": ("Rafale sans clé API (S8)", {}, TEXTE),
    # S7 : rafale AVEC clé valide -> DoS applicatif ; défense = limite de débit (429) + autoscaling
    "flood-valide": ("Rafale avec clé valide (S7, DoS)", {"X-API-Key": KEY}, TEXTE),
    # Mauvaises clés à répétition -> ne doit rien révéler, 401 constant
    "mauvaises-cles": ("Rafale de clés invalides", {"X-API-Key": "x" * 64}, TEXTE),
    # Payload maximal -> doit être refusé (422) sans erreur 500
    "gros-payload": ("Texte de 50 000 caractères", {"X-API-Key": KEY}, {"text": "idiot " * 9000}),
}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", choices=list(SCENARIOS) + ["tous"], default="tous")
    ap.add_argument("--users", type=int, default=30)
    ap.add_argument("--duree", type=int, default=20)
    args = ap.parse_args()

    print(f"Cible : {URL}  (ne lancer que contre une API dont on est responsable)")
    noms = list(SCENARIOS) if args.scenario == "tous" else [args.scenario]
    for cle in noms:
        titre, headers, payload = SCENARIOS[cle]
        await scenario(titre, headers, payload, args.users, args.duree)
        await asyncio.sleep(3)   # laisse l'API respirer entre deux scénarios


if __name__ == "__main__":
    asyncio.run(main())
