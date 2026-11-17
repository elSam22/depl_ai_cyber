"""Tests de la protection en entrée (limites de débit, clés fausses, taille, surcharge, en-têtes)."""
import asyncio
import os

os.environ["API_KEY"] = "test-key"
os.environ["METRICS_PORT"] = "0"

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import time  # noqa: E402

from limiteur_debit import LimiteurDebit, Sanctions, SeauJetons  # noqa: E402
from protection import Protection, empreinte, ip_client  # noqa: E402


def petite_app(**limites):
    app = FastAPI()

    @app.get("/x")
    def x():
        return {"ok": True}

    @app.post("/score")
    def score():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.add_middleware(Protection, **limites)
    return TestClient(app)


def lim(n):
    return LimiteurDebit(n, 60)


def test_limiteur_fenetre_glissante():
    l = LimiteurDebit(2, 60)
    assert l.autoriser("a")[0] and l.autoriser("a")[0]
    ok, attente = l.autoriser("a")
    assert not ok and attente > 0
    assert l.autoriser("b")[0]                      # un autre client n'est pas touché


def test_limite_par_ip_429_avec_retry_after():
    c = petite_app(limite_ip=lim(3), limite_score=lim(99), echecs=lim(99))
    assert [c.get("/x").status_code for _ in range(3)] == [200, 200, 200]
    r = c.get("/x")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


def test_limite_score_plus_stricte():
    c = petite_app(limite_ip=lim(99), limite_score=lim(2), echecs=lim(99))
    assert c.post("/score").status_code == 200 and c.post("/score").status_code == 200
    assert c.post("/score").status_code == 429
    assert c.get("/x").status_code == 200           # les autres routes restent disponibles


def test_health_jamais_limite():
    c = petite_app(limite_ip=lim(1), limite_score=lim(1), echecs=lim(1))
    assert all(c.get("/health").status_code == 200 for _ in range(20))   # sondes Kubernetes


def test_ip_bloquee_apres_trop_de_cles_fausses():
    echecs = lim(2)
    c = petite_app(limite_ip=lim(99), limite_score=lim(99), echecs=echecs)
    assert c.get("/x").status_code == 200
    echecs.enregistrer("testclient"); echecs.enregistrer("testclient")
    assert c.get("/x").status_code == 429
    assert c.get("/health").status_code == 200


def test_x_forwarded_for_avant_derniere_valeur():
    # Le load balancer Google ajoute « client, load balancer » : on ne croit pas les valeurs plus à gauche.
    c = petite_app(limite_ip=lim(1), limite_score=lim(99), echecs=lim(99))
    h = lambda ip: {"X-Forwarded-For": f"1.1.1.1, {ip}, 130.211.0.1"}   # noqa: E731
    assert c.get("/x", headers=h("9.9.9.9")).status_code == 200
    assert c.get("/x", headers=h("9.9.9.9")).status_code == 429          # même client malgré le champ inventé
    assert c.get("/x", headers=h("8.8.8.8")).status_code == 200          # autre client
    assert ip_client({"headers": [(b"x-forwarded-for", b"5.5.5.5, 130.211.0.1")]}) == "5.5.5.5"


def test_corps_trop_gros_413():
    c = petite_app(limite_ip=lim(99), limite_score=lim(99), echecs=lim(99), max_octets=100)
    assert c.post("/score", content=b"x" * 101).status_code == 413
    assert c.post("/score", content=b"x" * 50).status_code == 200


def test_en_tetes_de_securite():
    c = petite_app(limite_ip=lim(1), limite_score=lim(99), echecs=lim(99))
    for r in (c.get("/x"), c.get("/x")):            # réponse normale puis refus 429
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "max-age" in r.headers["strict-transport-security"]
        assert r.headers["cache-control"] == "no-store"


def test_empreinte_ne_contient_pas_l_ip():
    e = empreinte("203.0.113.7")
    assert "203" not in e and len(e) == 10 and e == empreinte("203.0.113.7")


def test_api_complete_cle_fausse_repetee_bloque(monkeypatch):
    import main
    from protection import ECHECS
    c = TestClient(main.app)
    ECHECS._historique.clear()
    ECHECS.max_requetes = 3
    try:
        codes = [c.get("/version", headers={"X-API-Key": "faux"}).status_code for _ in range(5)]
        assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]
        assert c.get("/health").status_code == 200
    finally:
        ECHECS.max_requetes = int(os.environ["LIMITE_ECHECS_PAR_MIN"])
        ECHECS._historique.clear()


def test_surcharge_renvoie_503(monkeypatch):
    import main
    monkeypatch.setattr(main, "INFERENCES", asyncio.Semaphore(0))   # aucune place de calcul
    monkeypatch.setattr(main, "ATTENTE_MAX_S", 0.05)
    r = TestClient(main.app).post("/score", json={"text": "hello"}, headers={"X-API-Key": "test-key"})
    assert r.status_code == 503 and r.headers["retry-after"] == "1"


def test_seau_rafale_puis_debit_lisse(monkeypatch):
    horloge = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: horloge[0])
    seau = SeauJetons(3, 1.0)                         # rafale de 3, puis 1 par seconde
    assert [seau.autoriser("a")[0] for _ in range(4)] == [True, True, True, False]
    horloge[0] += 1.0
    assert seau.autoriser("a")[0] and not seau.autoriser("a")[0]
    assert seau.autoriser("b")[0]                     # un autre client n'est pas touché


def test_sanction_progressive(monkeypatch):
    horloge = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: horloge[0])
    s = Sanctions(seuil_refus=3, fenetre_s=60, base_s=30, max_s=100, oubli_s=900)
    assert [s.enregistrer_refus("a") for _ in range(3)] == [0.0, 0.0, 30]
    assert s.bloque("a")[0]
    horloge[0] += 31
    assert not s.bloque("a")[0]
    assert [s.enregistrer_refus("a") for _ in range(3)][-1] == 60    # récidive : durée doublée
    horloge[0] += 61
    assert [s.enregistrer_refus("a") for _ in range(3)][-1] == 100   # plafond
    horloge[0] += 2000
    assert [s.enregistrer_refus("a") for _ in range(3)][-1] == 30    # oubliée après une longue période de calme


def test_client_qui_insiste_est_bloque_partout_sauf_health():
    c = petite_app(limite_ip=lim(2), limite_score=lim(99), echecs=lim(99), sanctions=Sanctions(seuil_refus=3))
    codes = [c.get("/x").status_code for _ in range(6)]
    assert codes[:2] == [200, 200] and set(codes[2:]) == {429}
    r = c.post("/score")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 25   # bloqué : même /score est refusé
    assert c.get("/health").status_code == 200
