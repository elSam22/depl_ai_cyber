"""Synthèse automatique des résultats : resultats/synthese.md (tableaux) et resultats/deni_service.png (courbes).

L'analyse (RedTeamIA/RAPPORT.md) est écrite à la main à partir de ces chiffres.
"""
import json

from commun import RESULTATS


def charger(nom):
    chemin = RESULTATS / f"{nom}.json"
    return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else None


def graphique(v7, v8):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tirs = [(n, d) for n, d in (("v7 : une adresse", v7), ("v8 : deux adresses", v8)) if d]
    if not tirs:
        return None
    fig, axes = plt.subplots(len(tirs), 1, figsize=(10, 3.6 * len(tirs)), squeeze=False)
    for ax, (titre, d) in zip(axes[:, 0], tirs):
        # Réponses de l'attaquant par seconde, cumulées sur les sources, par code
        cumul = {}
        for a in d["attaquants"].values():
            for s, codes in a.get("par_seconde", {}).items():
                for code, n in codes.items():
                    cumul.setdefault(code, {}).setdefault(int(s), 0)
                    cumul[code][int(s)] += n
        couleurs = {"200": "#2a78d6", "429": "#9aa5b1", "503": "#e0a030", "0": "#c0392b"}
        bas = None
        secondes = range(int(max((max(v) for v in cumul.values()), default=0)) + 1)
        import numpy as np
        bas = np.zeros(len(secondes))
        for code in sorted(cumul, key=lambda c: ("200", "503", "429", "0").index(c) if c in ("200", "503", "429", "0") else 9):
            vals = np.array([cumul[code].get(s, 0) for s in secondes])
            ax.bar(list(secondes), vals, bottom=bas, width=1.0, color=couleurs.get(code, "#555"), label=f"attaquant : {code}")
            bas += vals
        ax.set_ylabel("réponses / s (attaquant)")
        ax.set_xlabel("secondes depuis le début du tir")
        s = d["sonde_legitime"]
        ax.set_title(f"{titre} — utilisateur légitime : {s['pendant_attaque']['reussies']}/{s['pendant_attaque']['requetes']} "
                     f"réussies, P95 {s['reference']['p95_ms']} → {s['pendant_attaque']['p95_ms']} ms "
                     f"(×{s['multiplicateur_p95']})", fontsize=10)
        ax.legend(fontsize=8, loc="upper right")
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    chemin = RESULTATS / "deni_service.png"
    fig.savefig(chemin, dpi=130)
    return chemin


def main():
    l = ["# Synthèse automatique des vagues (chiffres bruts)", ""]
    for nom in ("v1_reconnaissance", "v2_sondes_web", "v3_authentification", "v4_fuite_information"):
        d = charger(nom)
        if d:
            l += [f"## {nom} — {d.get('verdict')}", ""] + [f"- {e}" for e in d.get("ecarts", [])] + [""]
    d = charger("v5_extraction")
    if d:
        l += ["## v5_extraction", "", f"- {d['reponses_exploitables']}/{d['requetes']} réponses exploitables en "
              f"{d['duree_s']} s, soit {d['exploitables_par_min']}/min ; codes {d['codes']} ; premier 429 à "
              f"{d['premier_429_apres_s']} s", ""]
    d = charger("v6_evasion_sondes_ia")
    if d:
        l += ["## v6_evasion_sondes_ia", "", "| Attaque | Résultat |", "|---|---|"]
        l += [f"| {k} | {v} |" for k, v in d["evasion"].items()]
        l += ["", f"Sondes IA ratées : {', '.join(d['sondes_ratees']) or 'aucune'}", ""]
    v7, v8 = charger("v7_deni_service"), charger("v8_multi_adresses")
    for nom, d in (("v7_deni_service", v7), ("v8_multi_adresses", v8)):
        if d:
            s = d["sonde_legitime"]
            l += [f"## {nom}", "",
                  f"- Attaque : {d['total_requetes_attaque']} requêtes, {d['total_acceptees_200']} acceptées (200)",
                  f"- Légitime pendant l'attaque : {s['pendant_attaque']}",
                  f"- Légitime référence : {s['reference']} ; multiplicateur P95 : ×{s['multiplicateur_p95']}",
                  f"- Alertes déclenchées : {d['supervision']['alertes_declenchees_s_apres_debut']}", ""]
    g = graphique(v7, v8)
    if g:
        l += [f"![Déni de service]({g.name})", ""]
    (RESULTATS / "synthese.md").write_text("\n".join(l), encoding="utf-8")
    print("-> RedTeamIA/resultats/synthese.md")


if __name__ == "__main__":
    main()
