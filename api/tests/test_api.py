"""Tests de l'API (cas du livrable 2 et de la grille de tests S1-S4).

Lancer depuis api/ :  pytest -v
"""
import os

os.environ["API_KEY"] = "test-key"

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app)
OK = {"X-API-Key": "test-key"}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_score_format():
    r = client.post("/score", json={"text": "Thanks for fixing the references."}, headers=OK)
    assert r.status_code == 200
    corps = r.json()
    assert 0 <= corps["score"] <= 100
    assert set(corps["labels"]) == {"toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"}
    assert isinstance(corps["toxique"], bool) and set(corps["seuils"]) == set(corps["labels"])
    assert set(corps["labels_detectes"]) <= set(corps["labels"])


def test_toxique_plus_haut_que_neutre():
    neutre = client.post("/score", json={"text": "Thanks for fixing the references."}, headers=OK).json()
    toxique = client.post("/score", json={"text": "You are a stupid idiot"}, headers=OK).json()
    assert toxique["score"] > neutre["score"]


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
