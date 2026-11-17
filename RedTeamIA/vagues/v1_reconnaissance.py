"""Vague 1 : reconnaissance (ce que voit un attaquant qui ne connaît que l'adresse).

Équivalent de la reconnaissance et des sondes web.* / nmap du professeur : routes documentées, documentation
interactive, fichiers sensibles connus des scanners, routes d'inférence « classiques » d'autres équipes, ports ouverts.
Attendu chez nous : seul /health répond 200 ; /version demande la clé ; tout le reste 404 ; ports 80 et 443 seuls.
"""
import socket
import time

from commun import client, ecrire, evenement, ip_cible, verifier_cible

# (méthode, chemin, code attendu). Les chemins viennent des listes classiques des scanners (nuclei, dirb).
CHEMINS = [
    ("GET", "/", 404), ("GET", "/health", 200), ("GET", "/version", 401), ("GET", "/score", 405),
    ("GET", "/docs", 404), ("GET", "/redoc", 404), ("GET", "/openapi.json", 404), ("GET", "/metrics", 404),
    ("POST", "/predict", 404), ("POST", "/v1/analyze", 404), ("POST", "/model", 404), ("POST", "/predire", 404),
    ("GET", "/.git/config", 404), ("GET", "/.env", 404), ("GET", "/phpinfo.php", 404), ("POST", "/xmlrpc.php", 404),
    ("GET", "/wp-login.php", 404), ("GET", "/admin", 404), ("GET", "/server-status", 404),
    ("GET", "/actuator/health", 404), ("GET", "/%2e%2e/%2e%2e/etc/passwd", 404),
]
# Ports testés (comme un « nmap » réduit) : 9090 est le port des métriques, qui ne doit PAS être public.
PORTS = [22, 80, 443, 3000, 5000, 8000, 8080, 8443, 9090]
EN_TETES_EMPREINTE = ["server", "x-powered-by", "via"]      # ce qui révèle la technologie employée


def scanner_ports(ip: str) -> dict:
    etat = {}
    for port in PORTS:
        try:
            with socket.create_connection((ip, port), timeout=3):
                etat[port] = "ouvert"
        except socket.timeout:
            etat[port] = "filtré"
        except OSError:
            etat[port] = "fermé"
    return etat


def main():
    verifier_cible()
    lignes, ecarts = [], []
    with client() as c:
        for methode, chemin, attendu in CHEMINS:
            r = c.request(methode, chemin)
            obtenu, note = r.status_code, None
            if r.status_code in (301, 302, 307, 308) and attendu != r.status_code:
                # Le load balancer de Google normalise les chemins (« %2e%2e » -> « .. » retiré) puis redirige :
                # on suit UNE fois pour voir ce que l'attaquant obtient au final.
                final = c.request(methode, r.headers.get("location", chemin))
                note = f"{r.status_code} (chemin normalisé par le load balancer) puis {final.status_code}"
                obtenu = final.status_code
            empreinte = {h: r.headers[h] for h in EN_TETES_EMPREINTE if h in r.headers}
            lignes.append({"methode": methode, "chemin": chemin, "attendu": attendu, "obtenu": obtenu, "note": note,
                           "taille": len(r.content), "empreinte": empreinte})
            evenement("test", vague="v1", nom=f"{methode} {chemin}", attendu=attendu, obtenu=obtenu, ok=obtenu == attendu)
            if obtenu != attendu:
                ecarts.append(f"{methode} {chemin} : {obtenu} (attendu {attendu})")
            time.sleep(0.2)      # rythme humain : la reconnaissance ne doit pas déclencher les limites
    ports = scanner_ports(ip_cible())
    for p, e in ports.items():
        evenement("test", vague="v1", nom=f"port {p}", attendu="ouvert" if p in (80, 443) else "fermé/filtré",
                  obtenu=e, ok=(e == "ouvert") == (p in (80, 443)))
    ouverts = [p for p, e in ports.items() if e == "ouvert"]
    if sorted(ouverts) != [80, 443]:
        ecarts.append(f"ports ouverts : {ouverts} (attendu [80, 443])")
    ecrire("v1_reconnaissance", {"routes": lignes, "ports": ports, "ecarts": ecarts,
                                 "verdict": "conforme" if not ecarts else f"{len(ecarts)} écart(s)"})
    for e in ecarts or ["aucun écart"]:
        print("  ", e)


if __name__ == "__main__":
    main()
