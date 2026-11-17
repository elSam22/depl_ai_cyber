"""Test du VRAI modèle : ignoré sans poids (api/model/ vide -> modèle factice), exécuté par la pipeline de déploiement."""
import os

import pytest

os.environ.setdefault("API_KEY", "test-key")
os.environ.setdefault("METRICS_PORT", "0")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

OK = {"X-API-Key": os.environ["API_KEY"]}


@pytest.mark.skipif(main.scorer.version.startswith("dummy"), reason="pas de poids dans api/model/ : modèle factice")
def test_modele_reel_separe_toxique_et_neutre():
    client = TestClient(main.app)
    t = client.post("/score", json={"text": "You are a stupid idiot"}, headers=OK).json()
    n = client.post("/score", json={"text": "Thanks for fixing the references, great work."}, headers=OK).json()
    version = client.get("/version", headers=OK).json()["model_version"]
    assert not version.startswith("dummy")
    assert t["toxique"] is True and t["score"] >= 90
    assert n["toxique"] is False and n["score"] <= 30


NEUTRE = ("The article was updated last week with new references from the library archive. "
          "Several editors discussed the formatting of the tables and agreed on a common style. ") * 20


@pytest.mark.skipif(main.scorer.version.startswith("dummy"), reason="pas de poids dans api/model/ : modèle factice")
@pytest.mark.parametrize("insulte", ["You are a stupid idiot and everyone hates you", "Shut up you pathetic moron"])
def test_noyage_detecte(insulte):
    """Défense anti-noyage : l'insulte placée après ~1 500 caractères neutres était tronquée, donc jamais vue."""
    r = TestClient(main.app).post("/score", json={"text": NEUTRE[:1500] + " " + insulte}, headers=OK).json()
    assert r["toxique"] is True


@pytest.mark.skipif(main.scorer.version.startswith("dummy"), reason="pas de poids dans api/model/ : modèle factice")
def test_texte_court_une_seule_passe():
    """Un texte court n'est lu qu'une fois : la défense ne coûte rien sur l'usage normal."""
    main.scorer.predict(["Thanks for fixing the references."])
    assert main.scorer.dernier_nb_passes == 1
