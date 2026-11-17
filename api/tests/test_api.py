"""Tests de l'API (cas du livrable 2 et de la grille de tests S1-S4).

Lancer depuis api/ :  pytest -v
"""
import os

os.environ["API_KEY"] = "test-key"
os.environ["LIMITE_IP_PAR_MIN"] = "100000"      # les tests de contrat ne doivent pas être freinés (test_protection.py teste les limites)
os.environ["LIMITE_SCORE_PAR_MIN"] = "100000"
os.environ["RAFALE_SCORE"] = "100000"
os.environ["LIMITE_ECHECS_PAR_MIN"] = "100000"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app)
OK = {"X-API-Key": "test-key"}


def test_health_ne_revele_rien():
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}      # ni version du modèle ni autre détail


def test_version_reservee_a_la_cle():
    assert client.get("/version").status_code == 401
    corps = client.get("/version", headers=OK).json()
    assert corps["model_version"] and "preprocessing_version" in corps


def test_score_format():
    r = client.post("/score", json={"text": "Thanks for fixing the references."}, headers=OK)
    assert r.status_code == 200
    corps = r.json()
    # Réponse pauvre (défense contre l'extraction) : score arrondi à la dizaine et verdict, rien d'autre
    assert set(corps) == {"score", "toxique"}
    assert isinstance(corps["score"], int) and 0 <= corps["score"] <= 100 and corps["score"] % 10 == 0
    assert isinstance(corps["toxique"], bool)


def test_toxique_plus_haut_que_neutre():
    neutre = client.post("/score", json={"text": "Thanks for fixing the references."}, headers=OK).json()
    toxique = client.post("/score", json={"text": "You are a stupid idiot"}, headers=OK).json()
    assert toxique["score"] > neutre["score"]


def test_cors_autorise_le_front():
    r = client.options("/score", headers={"Origin": "null", "Access-Control-Request-Method": "POST",
                                          "Access-Control-Request-Headers": "content-type,x-api-key"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "*"
    assert "x-api-key" in r.headers["access-control-allow-headers"].lower()


def test_sans_cle_401():                                   # S1
    assert client.post("/score", json={"text": "hi"}).status_code == 401


def test_mauvaise_cle_401():                               # S2
    assert client.post("/score", json={"text": "hi"}, headers={"X-API-Key": "faux"}).status_code == 401


def test_texte_vide_422():                                 # S4
    assert client.post("/score", json={"text": ""}, headers=OK).status_code == 422
    assert client.post("/score", json={"text": "   "}, headers=OK).status_code == 422


def test_texte_trop_long_422():                            # S4
    assert client.post("/score", json={"text": "a" * 6000}, headers=OK).status_code == 422


def test_json_invalide_422():                              # S4
    r = client.post("/score", content="pas du json", headers={**OK, "Content-Type": "application/json"})
    assert r.status_code == 422


def test_logs_sans_donnees_personnelles(caplog):           # S5
    client.post("/score", json={"text": "John Smith from 192.168.0.12 is a moron"}, headers=OK)
    assert "John" not in caplog.text and "192.168.0.12" not in caplog.text


def test_cle_non_ascii_refusee_proprement():
    """S2b : une clé avec un caractère non ASCII provoquait une erreur 500 (TypeError dans compare_digest)."""
    r = client.get("/version", headers={"X-API-Key": "clé-fausse-é".encode("utf-8")})
    assert r.status_code == 401


def test_json_trop_imbrique_refuse_proprement():
    """RedTeamIA, vague 4 : un JSON imbriqué sur 5 000 niveaux provoquait une erreur 500 (RecursionError)."""
    corps = ('{"text": ' + "[" * 5000 + "]" * 5000 + "}").encode()
    r = client.post("/score", content=corps, headers={**OK, "Content-Type": "application/json"})
    assert r.status_code == 422
