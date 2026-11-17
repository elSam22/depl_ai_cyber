"""Vague 3 : authentification (clé d'API) et force brute.

Variantes de clé absente ou mal formée, puis 30 clés fausses envoyées vite (force brute). Attendu : 401 pour chaque
clé fausse, puis 429 quand l'adresse dépasse 10 clés fausses par minute (par pod : avec 2 pods derrière le load
balancer, le blocage peut n'arriver qu'après ~20 essais). On vérifie aussi ce que subit alors un client LÉGITIME
qui partagerait l'adresse de l'attaquant (même box, même NAT).
"""
import time

from commun import CLE, client, ecrire, evenement, verifier_cible

TEXTE = {"text": "Thank you for the article"}


def main():
    verifier_cible()
    variantes, ecarts = {}, []
    with client() as c:
        essais = {
            "sans clé": {},
            "clé vide": {"X-API-Key": ""},
            "clé fausse": {"X-API-Key": "pas-la-bonne-cle"},
            "clé non ASCII (S2b)": {"X-API-Key": "clé-fausse-é".encode("utf-8")},
            "clé de 8 000 caractères": {"X-API-Key": "a" * 8000},
            "bonne clé + un caractère": {"X-API-Key": CLE + "x"},
            "bonne clé tronquée": {"X-API-Key": CLE[:-1]},
            "bonne clé en minuscules (si différente)": {"X-API-Key": CLE.lower()} if CLE.lower() != CLE else None,
        }
        for nom, entetes in essais.items():
            if entetes is None:
                continue
            r = c.post("/score", json=TEXTE, headers=entetes)
            variantes[nom] = r.status_code
            evenement("test", vague="v3", nom=nom, attendu=401, obtenu=r.status_code, ok=r.status_code == 401)
            if r.status_code == 200 or r.status_code >= 500:
                ecarts.append(f"{nom} : {r.status_code}")
            time.sleep(0.3)
        r = c.post(f"/score?api_key={CLE}", json=TEXTE)      # clé dans l'URL : ne doit pas être acceptée
        variantes["clé dans l'URL"] = r.status_code
        if r.status_code == 200:
            ecarts.append("clé acceptée dans l'URL (elle finirait dans les journaux)")

        # Force brute : 30 clés fausses, sans pause
        codes = []
        for i in range(30):
            codes.append(c.post("/score", json=TEXTE, headers={"X-API-Key": f"essai-{i:04d}"}).status_code)
            evenement("force_brute", essai=i + 1, code=codes[-1])
        premier_429 = next((i + 1 for i, code in enumerate(codes) if code == 429), None)
        # Juste après : un client légitime avec la BONNE clé, depuis la même adresse
        legitime_pendant = [c.post("/score", json=TEXTE, headers={"X-API-Key": CLE}).status_code for _ in range(4)]
        print("   force brute terminée, attente de 70 s (fin de la fenêtre de blocage)...", flush=True)
        time.sleep(70)
        legitime_apres = c.post("/score", json=TEXTE, headers={"X-API-Key": CLE}).status_code

    if premier_429 is None:
        ecarts.append("force brute : 30 clés fausses sans aucun blocage")
    ecrire("v3_authentification", {
        "variantes": variantes,
        "force_brute": {"essais": len(codes), "codes": codes, "nb_401": codes.count(401), "nb_429": codes.count(429),
                        "blocage_au_essai": premier_429},
        "client_legitime_meme_adresse": {"pendant_blocage": legitime_pendant, "apres_70s": legitime_apres},
        "ecarts": ecarts, "verdict": "conforme" if not ecarts else f"{len(ecarts)} écart(s)"})
    print(f"   force brute : {codes.count(401)} × 401, {codes.count(429)} × 429, blocage au {premier_429}e essai")
    print(f"   légitime même adresse : pendant {legitime_pendant}, après 70 s {legitime_apres}")
    for e in ecarts or ["aucun écart"]:
        print("  ", e)


if __name__ == "__main__":
    main()
