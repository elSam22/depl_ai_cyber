"""Rapport graphique d'un test de charge : tableau par palier + graphique, à partir des CSV de Locust.

Lancement (depuis la racine du projet) :
    .venv/bin/python loadtest/report.py montee2                       # montée progressive
    .venv/bin/python loadtest/report.py failover 12:41:30             # failover : heure UTC de la suppression du pod

Entrées (dans loadtest/results/) :
    <préfixe>_stats_history.csv   une ligne par seconde (nombre d'utilisateurs, requêtes/s), écrite par Locust
    <préfixe>_requetes.csv        UNE LIGNE PAR REQUÊTE (heure, durée, échec), écrite par le locustfile si LOG_REQUETES est défini
Sorties : <préfixe>_paliers.csv (tableau) et <préfixe>.png (graphique).

Les percentiles du CSV de Locust sont cumulés depuis le début du test : on ne s'en sert pas.
Tous les percentiles de ce rapport viennent du journal par requête.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")                          # pas de fenêtre : on écrit directement le fichier
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DOSSIER = Path(__file__).resolve().parent / "results"
PREFIXE = sys.argv[1] if len(sys.argv) > 1 else "montee2"
HEURE_INCIDENT = sys.argv[2] if len(sys.argv) > 2 else None      # failover : « HH:MM:SS » en UTC

# Paliers de la montée progressive (cohérents avec loadtest/montee.py) : (début s, fin s, utilisateurs)
PALIERS = [(0, 45, 1), (45, 105, 10), (105, 195, 50), (195, 300, 100)]
ECARTE_S = 10        # on ignore les 10 premières secondes de chaque palier (régime pas encore établi)
FENETRE_S = 10       # fenêtre glissante des courbes de latence

# Palette catégorielle validée (bleu, orange) + encre neutre ; erreurs en rouge uniquement avec libellé
BLEU, ORANGE, ROUGE, ENCRE, ENCRE_2, GRILLE = "#2a78d6", "#eb6834", "#e34948", "#0b0b0b", "#52514e", "#e4e3df"
FOND, BANDE = "#fcfcfb", "#f1f0ec"


def charger():
    h = pd.read_csv(DOSSIER / f"{PREFIXE}_stats_history.csv")
    h = h[h["Name"] == "Aggregated"].copy()
    # Avec l'interface web, Locust enregistre aussi l'attente avant le clic sur Start : le début du test est
    # la première seconde avec au moins un utilisateur.
    t0 = h[h["User Count"] > 0]["Timestamp"].iloc[0]
    h = h[h["Timestamp"] >= t0].copy()
    h["t"] = h["Timestamp"] - t0
    r = pd.read_csv(DOSSIER / f"{PREFIXE}_requetes.csv")
    r["t"] = r["heure_s"] - t0                                   # secondes depuis le début du test
    return h, r, t0


def tableau_paliers(r: pd.DataFrame, paliers=None) -> pd.DataFrame:
    lignes = []
    for debut, fin, util in (paliers or PALIERS):
        tout = r[(r.t >= debut) & (r.t < fin)]                   # requêtes terminées pendant le palier
        e = tout[tout.t >= debut + ECARTE_S]                     # régime établi
        d = e["duree_ms"]
        lignes.append({
            "palier (utilisateurs)": util,
            "requêtes": len(tout),
            "erreurs": int(tout["echec"].sum()),
            "requêtes/s": round(len(e) / max(fin - debut - ECARTE_S, 1), 1),
            "moyenne (ms)": round(d.mean()), "médiane (ms)": round(d.median()),
            "P95 (ms)": round(d.quantile(0.95)), "P99 (ms)": round(d.quantile(0.99)),
        })
    return pd.DataFrame(lignes)


def percentiles_glissants(r: pd.DataFrame, t_max: int) -> pd.DataFrame:
    """Médiane et P95 de la durée des requêtes terminées pendant les FENETRE_S dernières secondes."""
    sortie = []
    for t in range(FENETRE_S, t_max + 1):
        d = r[(r.t > t - FENETRE_S) & (r.t <= t)]["duree_ms"]
        if len(d) >= 3:
            sortie.append((t, d.median(), d.quantile(0.95)))
    return pd.DataFrame(sortie, columns=["t", "med", "p95"])


def style_axe(ax):
    ax.set_facecolor(FOND)
    for cote in ("top", "right"):
        ax.spines[cote].set_visible(False)
    for cote in ("left", "bottom"):
        ax.spines[cote].set_color(GRILLE)
    ax.tick_params(colors=ENCRE_2, labelsize=9)
    ax.grid(axis="y", color=GRILLE, linewidth=0.8)
    ax.set_axisbelow(True)


def axe_latence(ax, p):
    """Latence en échelle logarithmique (de quelques centaines de ms à plusieurs secondes sur le même axe)."""
    ax.plot(p.t, p.med, color=BLEU, linewidth=1.75, label="médiane")
    ax.plot(p.t, p.p95, color=ORANGE, linewidth=1.75, label="P95")
    ax.set_yscale("log")
    ax.set_ylabel("latence (ms, échelle log)", color=ENCRE_2)
    ax.set_yticks([100, 300, 1000, 3000, 10000])
    ax.set_yticklabels(["100", "300", "1 000", "3 000", "10 000"])
    ax.axhline(2000, color=ENCRE_2, linewidth=1, linestyle=(0, (4, 4)))
    ax.text(2, 2200, "seuil 2 s", color=ENCRE_2, fontsize=9)
    ax.legend(loc="upper left", frameon=False, labelcolor=ENCRE, fontsize=10, ncol=2)


def graphique_montee(h, r, chemin):
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(10, 9), sharex=True, facecolor=FOND,
                                     gridspec_kw={"height_ratios": [1, 2, 1.4], "hspace": 0.18})
    for ax in (a1, a2, a3):
        style_axe(ax)
        for i, (debut, fin, _) in enumerate(PALIERS):                # bandes alternées = paliers
            if i % 2 == 1:
                ax.axvspan(debut, fin, color=BANDE, zorder=0)
    a1.step(h.t, h["User Count"], where="post", color=ENCRE, linewidth=2)
    a1.set_ylabel("utilisateurs", color=ENCRE_2)
    a1.set_ylim(0, 115)
    for debut, fin, util in PALIERS:
        a1.text((debut + fin) / 2, util + 6, f"{util}", ha="center", color=ENCRE, fontsize=10, fontweight="bold")

    axe_latence(a2, percentiles_glissants(r, int(h.t.max())))

    a3.plot(h.t, h["Requests/s"], color=BLEU, linewidth=1.75)
    a3.set_ylabel("requêtes / s", color=ENCRE_2)
    a3.set_ylim(0, max(14, h["Requests/s"].max() * 1.15))
    a3.set_xlabel("temps depuis le début du test (s)", color=ENCRE_2)
    fig.suptitle("Montée progressive : 1 → 10 → 50 → 100 utilisateurs (API sur GKE)",
                 x=0.07, ha="left", color=ENCRE, fontsize=13, fontweight="bold", y=0.95)
    fig.savefig(chemin, dpi=160, facecolor=FOND, bbox_inches="tight")
    plt.close(fig)


def graphique_failover(h, r, t0, chemin):
    """Charge constante ; trait vertical = suppression du pod ; barres rouges = requêtes en erreur par seconde."""
    h_incident = datetime.strptime(HEURE_INCIDENT, "%H:%M:%S").time()
    jour = datetime.fromtimestamp(t0, timezone.utc).date()
    t_inc = datetime.combine(jour, h_incident, tzinfo=timezone.utc).timestamp() - t0

    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(10, 8.5), sharex=True, facecolor=FOND,
                                     gridspec_kw={"height_ratios": [1.8, 1.2, 1], "hspace": 0.2})
    for ax in (a1, a2, a3):
        style_axe(ax)
        ax.axvline(t_inc, color=ENCRE, linewidth=1.5, linestyle=(0, (5, 3)))
    axe_latence(a1, percentiles_glissants(r, int(h.t.max())))
    a1.text(t_inc + 2, a1.get_ylim()[1] * 0.75, "pod supprimé", color=ENCRE, fontsize=10, fontweight="bold")

    a2.plot(h.t, h["Requests/s"], color=BLEU, linewidth=1.75)
    a2.set_ylabel("requêtes / s", color=ENCRE_2)
    a2.set_ylim(0, max(8, h["Requests/s"].max() * 1.2))

    erreurs = r[r.echec == 1].groupby(r.t.astype(int)).size()
    a3.bar(erreurs.index, erreurs.values, width=1.0, color=ROUGE)
    a3.set_ylabel("erreurs / s", color=ENCRE_2)
    a3.set_ylim(0, max(3, erreurs.max() * 1.3 if len(erreurs) else 3))
    a3.text(0.01, 0.85, f"{int(r.echec.sum())} erreur(s) sur {len(r)} requêtes", transform=a3.transAxes,
            color=ENCRE, fontsize=10)
    a3.set_xlabel("temps depuis le début du test (s)", color=ENCRE_2)
    fig.suptitle("Failover : un des pods de l'API est supprimé pendant une charge constante (5 utilisateurs)",
                 x=0.07, ha="left", color=ENCRE, fontsize=13, fontweight="bold", y=0.95)
    fig.savefig(chemin, dpi=160, facecolor=FOND, bbox_inches="tight")
    plt.close(fig)
    return t_inc


def paliers_depuis_history(h: pd.DataFrame, duree_min: int = 10):
    """Paliers = suites de secondes avec le même nombre d'utilisateurs (on ignore les transitions courtes)."""
    paliers, debut, util = [], None, None
    for t, u in zip(h.t, h["User Count"]):
        if u != util:
            if util and debut is not None and t - debut >= duree_min:
                paliers.append((debut, t, int(util)))
            debut, util = t, u
    if util and debut is not None and h.t.iloc[-1] - debut >= duree_min:
        paliers.append((debut, h.t.iloc[-1], int(util)))
    return paliers


def graphique_stress(h, r, chemin, rupture):
    """Stress : le nombre d'utilisateurs monte par paliers jusqu'à la rupture (trait vertical)."""
    paliers = paliers_depuis_history(h)
    fig, (a1, a2, a3, a4) = plt.subplots(4, 1, figsize=(10, 10.5), sharex=True, facecolor=FOND,
                                         gridspec_kw={"height_ratios": [1, 2, 1.3, 0.8], "hspace": 0.2})
    for ax in (a1, a2, a3, a4):
        style_axe(ax)
        for i, (debut, fin, _) in enumerate(paliers):
            if i % 2 == 1:
                ax.axvspan(debut, fin, color=BANDE, zorder=0)
        if rupture:
            ax.axvline(rupture["t_s"], color=ENCRE, linewidth=1.5, linestyle=(0, (5, 3)))
    a1.step(h.t, h["User Count"], where="post", color=ENCRE, linewidth=2)
    a1.set_ylabel("utilisateurs", color=ENCRE_2)
    a1.set_ylim(0, max(30, h["User Count"].max() * 1.15))
    axe_latence(a2, percentiles_glissants(r, int(h.t.max())))
    if rupture:
        a2.text(rupture["t_s"] + 1, a2.get_ylim()[0] * 1.3, f"rupture : {rupture['utilisateurs']} utilisateurs",
                color=ENCRE, fontsize=10, fontweight="bold")
    a3.plot(h.t, h["Requests/s"], color=BLEU, linewidth=1.75)
    a3.set_ylabel("requêtes / s", color=ENCRE_2)
    a3.set_ylim(0, max(10, h["Requests/s"].max() * 1.2))
    erreurs = r[r.echec == 1].groupby(r.t.astype(int)).size()
    a4.bar(erreurs.index, erreurs.values, width=1.0, color=ROUGE)
    a4.set_ylabel("erreurs / s", color=ENCRE_2)
    a4.set_ylim(0, max(3, erreurs.max() * 1.3 if len(erreurs) else 3))
    a4.set_xlabel("temps depuis le début du test (s)", color=ENCRE_2)
    fig.suptitle("Stress : +10 utilisateurs toutes les 20 s jusqu'à la rupture (API sur GKE)",
                 x=0.07, ha="left", color=ENCRE, fontsize=13, fontweight="bold", y=0.95)
    fig.savefig(chemin, dpi=160, facecolor=FOND, bbox_inches="tight")
    plt.close(fig)
    return paliers


if __name__ == "__main__":
    h, r, t0 = charger()
    if PREFIXE.startswith("stress"):
        import json
        f = DOSSIER / "stress_rupture.json"
        rupture = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        paliers = graphique_stress(h, r, DOSSIER / f"{PREFIXE}.png", rupture)
        tab = tableau_paliers(r, paliers)
        tab.to_csv(DOSSIER / f"{PREFIXE}_paliers.csv", index=False)
        print(tab.to_string(index=False))
        print("rupture :", rupture)
    elif HEURE_INCIDENT:
        t_inc = graphique_failover(h, r, t0, DOSSIER / f"{PREFIXE}.png")
        avant = r[(r.t > t_inc - 30) & (r.t <= t_inc)]["duree_ms"]
        apres = r[(r.t > t_inc) & (r.t <= t_inc + 60)]["duree_ms"]
        print(f"incident à t = {t_inc:.0f} s | 30 s avant : médiane {avant.median():.0f} ms, P95 {avant.quantile(.95):.0f} ms"
              f" | 60 s après : médiane {apres.median():.0f} ms, P95 {apres.quantile(.95):.0f} ms")
        print(f"erreurs : {int(r.echec.sum())} sur {len(r)} requêtes ; dernière erreur à t = "
              f"{r[r.echec == 1].t.max() if r.echec.sum() else float('nan'):.0f} s")
    else:
        tab = tableau_paliers(r)
        tab.to_csv(DOSSIER / f"{PREFIXE}_paliers.csv", index=False)
        print(tab.to_string(index=False))
        graphique_montee(h, r, DOSSIER / f"{PREFIXE}.png")
    print(f"\nÉcrit : {DOSSIER / (PREFIXE + '.png')}")
