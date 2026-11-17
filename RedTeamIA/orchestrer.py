"""Lance les vagues du Red Team interne, dans l'ordre qui évite de fausser les mesures.

    URL=https://<adresse> API_KEY=... .venv/bin/python RedTeamIA/orchestrer.py            # vagues 1 à 6 (sans impact)
    URL=... API_KEY=... .venv/bin/python RedTeamIA/orchestrer.py --impact                 # + vagues 7 et 8 (charge)
    URL=... API_KEY=... .venv/bin/python RedTeamIA/orchestrer.py --vague v3               # une seule vague

Ordre : les vagues qui ont besoin d'une adresse « propre » (évasion) passent AVANT celles qui font bloquer notre
adresse (force brute, extraction, déni de service), sinon on mesurerait nos propres refus.
"""
import argparse
import importlib
import signal
import sys
import time
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
sys.path[:0] = [str(DOSSIER), str(DOSSIER / "vagues")]

from commun import RESULTATS, evenement, resume  # noqa: E402

# Arrêt demandé (bouton de l'interface, Ctrl+C) : on sort proprement pour que les pods du test soient supprimés.
signal.signal(signal.SIGTERM, lambda *_: sys.exit(130))

SANS_IMPACT = ["v1_reconnaissance", "v2_sondes_web", "v4_fuite_information", "v6_evasion_sondes_ia",
               "v3_authentification", "v5_extraction"]


def lancer(module: str, *args):
    print(f"\n######## {module}", flush=True)
    t0 = time.time()
    evenement("vague", module=module, etat="en cours")
    m = importlib.import_module(module)
    try:
        m.main(*args)
    except SystemExit as e:
        evenement("vague", module=module, etat="arrêtée", detail=str(e))
        raise
    for nom in (["v7_deni_service", "v8_multi_adresses"] if module.startswith("v7") else [module]):
        chemin = RESULTATS / f"{nom}.json"
        if chemin.exists() and chemin.stat().st_mtime >= t0:
            evenement("vague", module=nom, etat="terminée", resume=resume(nom))
    print(f"   ({time.time() - t0:.0f} s)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impact", action="store_true", help="ajoute les vagues 7 et 8 (déni de service)")
    ap.add_argument("--vague", help="v1 ... v8 : une seule vague")
    ap.add_argument("--depuis", help="reprendre la campagne à partir de cette vague (ordre de la campagne)")
    a = ap.parse_args()
    if a.vague:
        if a.vague in ("v7", "v8"):
            lancer("v7_v8_deni_service", (a.vague,))
        else:
            lancer(next(m for m in SANS_IMPACT if m.startswith(a.vague + "_")))
        return
    ordre = SANS_IMPACT + (["v7_v8_deni_service"] if a.impact else [])
    if a.depuis:
        ordre = ordre[next(i for i, m in enumerate(ordre) if m.startswith(a.depuis)):]
    for m in [m for m in ordre if m in SANS_IMPACT]:
        lancer(m)
    if "v7_v8_deni_service" in ordre:
        print("\n   pause de 120 s : fin des blocages causés par la force brute et l'extraction", flush=True)
        time.sleep(120)
        lancer("v7_v8_deni_service", ("v7", "v8"))
    lancer("rapport")


if __name__ == "__main__":
    main()
