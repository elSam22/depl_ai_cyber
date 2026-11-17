"""Interface du Red Team interne : lance les vagues et diffuse leurs mesures en direct au tableau de bord.

    export URL=https://<adresse de NOTRE API>
    export API_KEY="$(kubectl get secret dss-api-key -o jsonpath='{.data.API_KEY}' | base64 -d)"
    .venv/bin/python RedTeamIA/interface/serveur.py          # puis http://127.0.0.1:8060

Sécurité de l'interface elle-même :
- elle n'écoute que sur 127.0.0.1 (jamais sur le réseau) ;
- la clé reste dans l'environnement du serveur, elle n'est jamais envoyée au navigateur ;
- les actions (lancer, arrêter) exigent l'en-tête X-RedTeam : une page d'un autre site ouverte dans le même navigateur
  ne peut pas l'envoyer sans autorisation CORS, que ce serveur ne donne jamais (protection contre le CSRF).
"""
import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

ICI = Path(__file__).resolve().parent
REDTEAM = ICI.parent
sys.path.insert(0, str(REDTEAM))
from commun import CLE, RESULTATS, URL, masquer, resume  # noqa: E402

NOMS = ["v1_reconnaissance", "v2_sondes_web", "v3_authentification", "v4_fuite_information", "v5_extraction",
        "v6_evasion_sondes_ia", "v7_deni_service", "v8_multi_adresses"]
MAX_HISTORIQUE = 60_000

app = FastAPI(title="RedTeamIA", docs_url=None, redoc_url=None, openapi_url=None)


class Execution:
    """Une seule campagne à la fois : son processus, l'historique de ses événements et les navigateurs abonnés."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.mode = None
        self.debut = None
        self.historique: list[dict] = []
        self.abonnes: set[asyncio.Queue] = set()
        self.boucle: asyncio.AbstractEventLoop | None = None
        self.verrou = threading.Lock()

    def en_cours(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def publier(self, ev: dict):
        with self.verrou:
            self.historique.append(ev)
            if len(self.historique) > MAX_HISTORIQUE:
                del self.historique[: MAX_HISTORIQUE // 10]
        if self.boucle:
            for q in list(self.abonnes):
                self.boucle.call_soon_threadsafe(q.put_nowait, ev)

    def lire_sortie(self, proc: subprocess.Popen):
        """Fil de lecture : chaque ligne du processus devient un événement (mesure « @@EVT » ou ligne de journal)."""
        for ligne in proc.stdout:
            # Une trace d'erreur peut recopier un en-tête : on retire la clé et l'adresse de TOUTE ligne avant de la
            # diffuser (incident du 17 novembre : une trace de httpx contenait la clé).
            ligne = masquer(ligne.rstrip("\n"))
            if ligne.startswith("@@EVT "):
                try:
                    self.publier(json.loads(ligne[6:]))
                    continue
                except json.JSONDecodeError:
                    pass
            if ligne.strip():
                self.publier({"type": "log", "t": round(time.time(), 2), "texte": ligne})
        code = proc.wait()
        self.publier({"type": "fin_execution", "t": round(time.time(), 2), "code": code})


EXEC = Execution()


class Demande(BaseModel):
    mode: str                 # « sans_impact », « complet » ou « vague »
    vague: str | None = None  # v1 ... v8 si mode = « vague »
    depuis: str | None = None  # reprendre une campagne à partir de cette vague (v1 ... v7)


def verifier_action(x_redteam: str | None):
    if x_redteam != "1":
        raise HTTPException(403, "en-tête X-RedTeam manquant")


@app.get("/")
def page():
    return FileResponse(ICI / "dashboard.html")


@app.get("/etat")
def etat():
    resultats = {}
    for nom in NOMS:
        if (RESULTATS / f"{nom}.json").exists():
            try:
                resultats[nom] = resume(nom)
            except (KeyError, json.JSONDecodeError):
                pass
    return {"en_cours": EXEC.en_cours(), "mode": EXEC.mode, "debut": EXEC.debut,
            "cible_configuree": URL.startswith("https://"), "cle_configuree": bool(CLE), "resultats": resultats}


@app.post("/lancer")
def lancer(d: Demande, x_redteam: str | None = Header(default=None)):
    verifier_action(x_redteam)
    if not (URL.startswith("https://") and CLE):
        raise HTTPException(400, "URL et API_KEY non définies dans l'environnement du serveur (voir README)")
    if EXEC.en_cours():
        raise HTTPException(409, "une campagne est déjà en cours")
    args = {"sans_impact": [], "complet": ["--impact"]}.get(d.mode)
    if args is not None and d.depuis:
        args = args + ["--depuis", d.depuis]
    if args is None:
        if d.mode != "vague" or d.vague not in [f"v{i}" for i in range(1, 9)]:
            raise HTTPException(422, "mode ou vague inconnus")
        args = ["--vague", d.vague]
    env = os.environ | {"REDTEAM_FLUX": "1", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen([sys.executable, str(REDTEAM / "orchestrer.py"), *args], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=env, cwd=REDTEAM.parent, start_new_session=True)
    with EXEC.verrou:
        EXEC.historique = []
    EXEC.proc, EXEC.mode, EXEC.debut = proc, d.mode if d.mode != "vague" else d.vague, time.time()
    EXEC.publier({"type": "debut_execution", "t": round(time.time(), 2), "mode": EXEC.mode})
    threading.Thread(target=EXEC.lire_sortie, args=(proc,), daemon=True).start()
    return {"ok": True, "mode": EXEC.mode}


@app.post("/arreter")
def arreter(x_redteam: str | None = Header(default=None)):
    verifier_action(x_redteam)
    if not EXEC.en_cours():
        return {"ok": False, "detail": "rien en cours"}
    proc = EXEC.proc
    proc.send_signal(signal.SIGTERM)       # l'orchestrateur sort proprement : les pods du test sont supprimés
    EXEC.publier({"type": "log", "t": round(time.time(), 2), "texte": "ARRÊT D'URGENCE demandé : nettoyage en cours"})

    def forcer():
        try:
            proc.wait(90)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
    threading.Thread(target=forcer, daemon=True).start()
    return {"ok": True}


@app.get("/flux")
async def flux():
    """Flux SSE : l'historique de la campagne en cours, puis chaque nouvel événement."""
    EXEC.boucle = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()
    with EXEC.verrou:
        passe = list(EXEC.historique)
        EXEC.abonnes.add(q)

    async def generer():
        try:
            yield "event: rejeu\ndata: " + json.dumps(passe, ensure_ascii=False) + "\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"
                except asyncio.TimeoutError:
                    yield ": battement\n\n"        # garde la connexion ouverte
        finally:
            EXEC.abonnes.discard(q)
    return StreamingResponse(generer(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT_INTERFACE", "8060")), log_level="warning")
