"""Vague 2 : sondes web (en-têtes de sécurité, HTTPS, CORS, méthodes, pare-feu applicatif).

Le professeur avait relevé chez nous : « en-têtes manquants (HSTS, CSP, X-Frame-Options, X-Content-Type-Options) » et
« aucun WAF ». On vérifie les en-têtes sur trois types de réponse (200, 404, 401), car une réponse d'erreur produite
avant l'application peut les perdre.
"""
import socket
import ssl
import time

import httpx

from commun import AGENT, HOTE, client, ecrire, evenement, verifier_cible

REQUIS = ["strict-transport-security", "content-security-policy", "x-content-type-options", "x-frame-options",
          "referrer-policy", "cache-control"]
INTERDITS = ["x-powered-by"]
# Charges classiques qu'un pare-feu applicatif (WAF) bloquerait : ici elles arrivent jusqu'à l'API, qui les ignore.
CHARGES_WAF = {"xss": "/health?q=<script>alert(1)</script>", "sqli": "/health?id=1' OR '1'='1",
               "traversee": "/health?f=../../../../etc/passwd"}


def tls() -> dict:
    """Version de TLS négociée, suite de chiffrement, échéance du certificat."""
    ctx = ssl.create_default_context()
    with socket.create_connection((HOTE, 443), timeout=10) as s, ctx.wrap_socket(s, server_hostname=HOTE) as t:
        cert = t.getpeercert()
        return {"version": t.version(), "chiffrement": t.cipher()[0], "expire": cert.get("notAfter"),
                "emetteur": dict(x[0] for x in cert.get("issuer", []))}


def main():
    verifier_cible()
    resultats, ecarts = {}, []
    with client() as c:
        reponses = {"200 /health": c.get("/health"), "404 /inconnu": c.get("/inconnu"),
                    "401 /score sans clé": c.post("/score", json={"text": "bonjour"})}
        for nom, r in reponses.items():
            manquants = [h for h in REQUIS if h not in r.headers]
            presents_interdits = [h for h in INTERDITS if h in r.headers]
            serveur = r.headers.get("server")
            resultats[nom] = {"code": r.status_code, "manquants": manquants, "interdits": presents_interdits,
                              "server": serveur}
            evenement("test", vague="v2", nom=f"en-têtes {nom}", attendu="6 en-têtes", obtenu=f"{6 - len(manquants)}/6",
                      ok=not manquants)
            if manquants:
                ecarts.append(f"{nom} : en-têtes manquants {manquants}")
            if presents_interdits or (serveur and any(ch.isdigit() for ch in serveur)):
                ecarts.append(f"{nom} : empreinte technique ({presents_interdits or serveur})")
            time.sleep(0.2)

        # HTTP en clair : doit rediriger vers HTTPS
        r = httpx.get(f"http://{HOTE}/health", follow_redirects=False, timeout=10, headers={"User-Agent": AGENT})
        resultats["http_clair"] = {"code": r.status_code, "location_https": r.headers.get("location", "").startswith("https://")}
        evenement("test", vague="v2", nom="HTTP -> HTTPS", attendu=301, obtenu=r.status_code,
                  ok=r.status_code in (301, 308))
        if r.status_code not in (301, 308) or not resultats["http_clair"]["location_https"]:
            ecarts.append(f"HTTP en clair : {r.status_code} sans redirection HTTPS")

        # CORS : une page d'un autre site peut-elle appeler l'API depuis un navigateur ?
        r = c.options("/score", headers={"Origin": "https://site-malveillant.example", "Access-Control-Request-Method": "POST",
                                         "Access-Control-Request-Headers": "X-API-Key, Content-Type"})
        resultats["cors"] = {"code": r.status_code, "allow_origin": r.headers.get("access-control-allow-origin"),
                             "allow_credentials": r.headers.get("access-control-allow-credentials")}

        # Méthodes inattendues
        resultats["methodes"] = {m: c.request(m, "/score").status_code for m in ("PUT", "DELETE", "TRACE")}

        # Pare-feu applicatif : la charge arrive-t-elle jusqu'à l'application ?
        resultats["waf"] = {nom: c.get(chemin).status_code for nom, chemin in CHARGES_WAF.items()}
        for nom, code in resultats["waf"].items():
            evenement("test", vague="v2", nom=f"WAF : charge {nom}", attendu="bloquée", obtenu=code, ok=code != 200)
        if all(code == 200 for code in resultats["waf"].values()):
            ecarts.append("pas de pare-feu applicatif (WAF) : charges XSS / SQLi transmises à l'API (risque connu, accepté)")

    resultats["tls"] = tls()
    ecrire("v2_sondes_web", {"resultats": resultats, "ecarts": ecarts,
                             "verdict": "conforme" if not ecarts else f"{len(ecarts)} écart(s)"})
    for e in ecarts or ["aucun écart"]:
        print("  ", e)


if __name__ == "__main__":
    main()
