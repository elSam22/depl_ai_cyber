"""Vague 4 : fuite d'information et entrées malformées.

Le professeur a trouvé chez d'autres équipes des réponses qui exposaient le score exact, le seuil de décision et le nom
du modèle (précondition du vol de modèle et du contournement). On vérifie que notre réponse ne contient que
`score` (arrondi à la dizaine) et `toxique`, et que les erreurs ne révèlent rien (trace Python, chemins de fichiers).
On envoie aussi des corps JSON anormaux, dont un JSON très imbriqué, classique pour provoquer une erreur 500.
"""
import time

from commun import CLE, client, ecrire, evenement, verifier_cible

CHAMPS_AUTORISES = {"score", "toxique"}
SIGNES_DE_FUITE = ["Traceback", "File \"/", "/app/", ".py\"", "torch", "distilbert", "seuil", "proba"]

CORPS_ANORMAUX = {
    "texte vide": '{"text": ""}',
    "texte nombre": '{"text": 123}',
    "texte liste": '{"text": ["a"]}',
    "texte nul": '{"text": null}',
    "champ en trop": '{"text": "hello", "modele": "laya", "debug": true}',
    "JSON invalide": '{"text": "hello"',
    "JSON imbriqué 5 000 niveaux": '{"text": ' + "[" * 5000 + "]" * 5000 + "}",
    "texte de 5 001 caractères": '{"text": "' + "a" * 5001 + '"}',
    "octet nul": '{"text": "hello\\u0000world"}',
}


def main():
    verifier_cible()
    ecarts, reponses = [], {}
    entetes = {"X-API-Key": CLE, "Content-Type": "application/json"}
    with client() as c:
        for nom, texte in [("toxique", "You are a stupid idiot"), ("sain", "Thank you for your help")]:
            r = c.post("/score", json={"text": texte}, headers={"X-API-Key": CLE})
            corps = r.json() if r.status_code == 200 else {}
            champs = set(corps)
            reponses[nom] = {"code": r.status_code, "corps": corps, "en_tetes": sorted(r.headers.keys())}
            evenement("test", vague="v4", nom=f"réponse {nom} : champs", attendu="score, toxique",
                      obtenu=", ".join(sorted(champs)), ok=not (champs - CHAMPS_AUTORISES))
            if champs - CHAMPS_AUTORISES:
                ecarts.append(f"réponse {nom} : champs en trop {sorted(champs - CHAMPS_AUTORISES)}")
            if isinstance(corps.get("score"), (int, float)) and corps["score"] % 10:
                ecarts.append(f"réponse {nom} : score non arrondi ({corps['score']})")
            time.sleep(1.2)

        anormaux = {}
        for nom, brut in CORPS_ANORMAUX.items():
            r = c.post("/score", content=brut.encode(), headers=entetes)
            fuite = [s for s in SIGNES_DE_FUITE if s.lower() in r.text.lower()]
            anormaux[nom] = {"code": r.status_code, "taille_reponse": len(r.content), "indices_de_fuite": fuite}
            evenement("test", vague="v4", nom=nom, attendu="< 500, sans fuite", obtenu=r.status_code,
                      ok=r.status_code < 500 and not fuite)
            if r.status_code >= 500:
                ecarts.append(f"{nom} : erreur serveur {r.status_code}")
            if fuite:
                ecarts.append(f"{nom} : la réponse contient {fuite}")
            if nom == "champ en trop" and r.status_code == 200:
                anormaux[nom]["note"] = "champs inconnus ignorés (pas de 422) : sans effet sur le modèle choisi"
            time.sleep(1.2)      # sous la limite de /score : on ne veut pas mesurer nos propres 429

        r = c.get("/version", headers={"X-API-Key": CLE})
        version = {"code": r.status_code, "corps": r.json() if r.status_code == 200 else None}

    ecrire("v4_fuite_information", {"reponses_valides": reponses, "corps_anormaux": anormaux,
                                    "version_avec_cle": version, "ecarts": ecarts,
                                    "verdict": "conforme" if not ecarts else f"{len(ecarts)} écart(s)"})
    for e in ecarts or ["aucun écart"]:
        print("  ", e)


if __name__ == "__main__":
    main()
