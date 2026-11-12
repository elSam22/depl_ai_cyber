"""Schéma d'architecture cloud — Digital Social Score (étape 7).
Lancement : .venv/bin/python images/architecture_cloud.py
"""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

SORTIE = Path(__file__).resolve().parent / "architecture_cloud.png"

# ── Palette ──────────────────────────────────────────────────────────────────
FOND        = "#f9f9f7"
ENCRE       = "#1a1a18"
GRIS_TEXTE  = "#555550"
VERT        = "#1a7a4a"   # flux sécurisés (HTTPS, secrets)
ROUGE       = "#c0392b"   # HTTP non chiffré
BLEU        = "#2a6db5"   # flux numérotés (requête client)
ORANGE      = "#d4680a"   # supervision (pointillés / à faire)
JAUNE_FOND  = "#fff8ed"
BLEU_FOND   = "#edf3fb"
GRIS_FOND   = "#f0efec"

fig, ax = plt.subplots(figsize=(18, 11), facecolor=FOND)
ax.set_xlim(0, 100)
ax.set_ylim(0, 68)
ax.axis("off")

# ── Helpers ───────────────────────────────────────────────────────────────────
def boite(x, y, w, h, titre, lignes=(), fc="#ffffff", ec=ENCRE,
          pointille=False, taille=9.5, gras=True, ecw=1.5):
    ls = (0, (5, 3)) if pointille else "-"
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.3,rounding_size=0.8",
                                fc=fc, ec=ec, lw=ecw, ls=ls, zorder=2))
    ax.text(x + w/2, y + h - 1.3, titre, ha="center", va="top",
            fontsize=taille, fontweight="bold" if gras else "normal",
            color=ENCRE, zorder=3)
    for i, l in enumerate(lignes):
        ax.text(x + w/2, y + h - 3.2 - 1.7*i, l, ha="center", va="top",
                fontsize=8, color=GRIS_TEXTE, zorder=3)

def zone(x, y, w, h, label, fc):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.3,rounding_size=1.2",
                                fc=fc, ec="#c8c8c0", lw=1.2, zorder=1))
    ax.text(x + 1, y + h - 0.9, label, ha="left", va="top",
            fontsize=8.5, color=GRIS_TEXTE, fontstyle="italic", zorder=2)

def fleche(x1, y1, x2, y2, couleur=ENCRE, pointille=False, lw=1.8):
    ls = (0, (4, 3)) if pointille else "-"
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=couleur,
                                lw=lw, ls=ls, shrinkA=0, shrinkB=0),
                zorder=4)

def badge(x, y, texte, couleur):
    ax.add_patch(plt.Circle((x, y), 1.1, fc=couleur, ec="white",
                            lw=1.4, zorder=5))
    ax.text(x, y, texte, ha="center", va="center", fontsize=8.5,
            color="white", fontweight="bold", zorder=6)

def etiquette(x, y, texte, couleur, ha="center", taille=7.8, gras=False):
    ax.text(x, y, texte, ha=ha, va="center", fontsize=taille,
            color=couleur, fontweight="bold" if gras else "normal", zorder=5)

# ── Zones ─────────────────────────────────────────────────────────────────────
zone(16, 1, 83, 63, "Google Cloud Platform — région europe-west9 (Paris, France) — données dans l'UE", BLEU_FOND)
zone(61, 12, 36.5, 44, "Cluster GKE Autopilot — Kubernetes géré", JAUNE_FOND)

# ── Composants principaux ─────────────────────────────────────────────────────
# Client
boite(1, 29, 13, 10, "Client",
      ["navigateur,", "curl, app"], fc=GRIS_FOND, ec="#888880")

# Load Balancer
boite(19, 29, 18, 10, "Load Balancer HTTPS",
      ["Ingress Google", "IP fixe, certificat géré", "HTTP → HTTPS forcé"],
      fc="#ffffff")

# Service K8s
boite(42, 29, 15, 10, "Service dss-api",
      ["ClusterIP :80→8080", "pods prêts uniquement"],
      fc="#ffffff")

# Pods
boite(63, 15, 33, 42, "Pods dss-api  (2 à 5)",
      ["autoscaler HPA : 70 % CPU", "conteneur non-root, drop ALL"],
      fc="#fffdf8", ec="#b08030", taille=10)

# Étapes dans le pod
etapes_pod = [
    ("a", "Vérif. clé  X-API-Key  →  401 si absente/fausse", ROUGE),
    ("b", "Validation entrée  1–5 000 car.  →  422 si KO",   ENCRE),
    ("c", "Anonymisation : spaCy NER + regex  →  8 balises",  VERT),
    ("d", "Nettoyage : minuscules, emojis, ponctuation",       ENCRE),
    ("e", "DistilBERT : 6 probabilités (multi-label)",         BLEU),
    ("f", "Seuils par label → score 0-100",                    BLEU),
]
for i, (lettre, texte, coul) in enumerate(etapes_pod):
    yy = 47 - 4.5*i
    ax.add_patch(plt.Circle((66.5, yy), 0.9, fc=coul, ec="white", lw=1.2, zorder=5))
    ax.text(66.5, yy, lettre, ha="center", va="center",
            fontsize=7.5, color="white", fontweight="bold", zorder=6)
    etiquette(68, yy, texte, ENCRE, ha="left", taille=7.8)

etiquette(66.5, 20.5, "Sondes /health : startupProbe · readinessProbe · livenessProbe",
          GRIS_TEXTE, ha="left", taille=7.5)

# Secret Manager
boite(63, 3, 33, 8.5, "Secret Manager → Secret Kubernetes",
      ["clé API hors code et hors Git", "injectée via variable d'env. API_KEY"],
      fc="#ffffff", ec=VERT, ecw=1.4)

# Artifact Registry + Cloud Build
boite(19, 3, 13, 8, "Cloud Build",
      ["image construite", "sans install locale"], fc="#ffffff")
boite(37, 3, 18, 8, "Artifact Registry",
      ["image : code + modèle", "(aucun DL au démarrage)"], fc="#ffffff")

# Cloud Logging
boite(63, 57.5, 33, 7, "Cloud Logging",
      ["score · longueur · durée — jamais le texte"], fc="#ffffff", ec=VERT)

# Supervision (pointillés)
boite(35, 46, 20, 9, "Supervision (étape 6)",
      ["Prometheus + Grafana :", "req/s, latence, erreurs, CPU"],
      fc="#fff4e8", ec=ORANGE, pointille=True, ecw=1.6)

# ── Flux numérotés (requête) ──────────────────────────────────────────────────
# 1 Client → LB  (HTTPS)
fleche(14, 34, 19, 34, couleur=VERT, lw=2)
badge(16.5, 36.2, "1", BLEU)
etiquette(16.5, 37.8, "HTTPS ✓", VERT, taille=7.5, gras=True)
etiquette(16.5, 36.9, "chiffré", VERT, taille=7)

# 2 LB → Service  (HTTP interne)
fleche(37, 34, 42, 34, couleur=ROUGE, lw=2)
badge(39.5, 36.2, "2", BLEU)
etiquette(39.5, 37.8, "HTTP ✗", ROUGE, taille=7.5, gras=True)
etiquette(39.5, 36.9, "réseau Google interne", ROUGE, taille=7)

# 3 Service → Pods  (HTTP interne)
fleche(57, 34, 63, 34, couleur=ROUGE, lw=2)
badge(60, 36.2, "3", BLEU)
etiquette(60, 37.8, "HTTP ✗", ROUGE, taille=7.5, gras=True)
etiquette(60, 36.9, "réseau Google interne", ROUGE, taille=7)
# Auth marker
etiquette(60, 35.9, "→ auth en (a)", ROUGE, taille=7)

# 4 Réponse JSON (HTTPS, retour)
ax.plot([79.5, 8], [27, 27], color=VERT, lw=2, solid_capstyle="butt", zorder=4)
fleche(8, 27, 8, 29, couleur=VERT, lw=2)
badge(43, 27.5, "4", BLEU)
etiquette(43, 25.8, "réponse HTTPS : score, labels, seuils, labels_detectes, model_version",
          VERT, taille=7.5)

# ── Flux infrastructure (vert) ────────────────────────────────────────────────
# A : Secret → Pods
fleche(79.5, 11.5, 79.5, 15, couleur=VERT, lw=1.6)
badge(79.5, 13.0, "A", VERT)
etiquette(81, 13.0, "injection secret", VERT, ha="left", taille=7.5)

# B : Artifact Registry → Pods
fleche(55, 7, 63, 20, couleur=VERT, lw=1.6)
badge(60, 15, "B", VERT)
etiquette(61, 13.5, "image Docker", VERT, ha="left", taille=7.5)

# Cloud Build → Artifact Registry
fleche(32, 7, 37, 7, couleur=ENCRE, lw=1.4)

# C : Pods → Cloud Logging
fleche(79.5, 57, 79.5, 57.5, couleur=VERT, lw=1.6)
badge(79.5, 57.1, "C", VERT)

# Supervision pointillés
fleche(63, 36.5, 55, 48, couleur=ORANGE, pointille=True, lw=1.4)

# ── Légende ───────────────────────────────────────────────────────────────────
lx, ly, lw2, lh = 1, 1, 14, 24
ax.add_patch(FancyBboxPatch((lx, ly), lw2, lh,
                            boxstyle="round,pad=0.3,rounding_size=0.5",
                            fc="#f4f4f1", ec="#aaaaaa", lw=1, zorder=2))
ax.text(lx + lw2/2, ly + lh - 0.8, "Légende", ha="center", va="top",
        fontsize=9, fontweight="bold", color=ENCRE, zorder=3)

legende_items = [
    ("1–4", "Flux requête/réponse",        BLEU),
    ("a–f", "Étapes dans le pod",           ENCRE),
    ("A",   "Secret → pods",               VERT),
    ("B",   "Image → nœuds",              VERT),
    ("C",   "Logs → Cloud Logging",        VERT),
    ("▬",   "HTTPS (chiffré)",             VERT),
    ("▬",   "HTTP (réseau interne)",       ROUGE),
    ("╌",   "Non installé",               ORANGE),
]
for i, (sym, desc, coul) in enumerate(legende_items):
    yy = ly + lh - 2.5 - 2.5*i
    ax.text(lx + 1.2, yy, sym, ha="left", va="center",
            fontsize=8.5, color=coul, fontweight="bold", zorder=3)
    ax.text(lx + 3.5, yy, desc, ha="left", va="center",
            fontsize=7.8, color=ENCRE, zorder=3)

# ── Titre ─────────────────────────────────────────────────────────────────────
ax.text(1, 67.5, "Digital Social Score — Architecture cloud (étape 7)",
        fontsize=14, fontweight="bold", color=ENCRE, va="top")

fig.savefig(SORTIE, dpi=140, facecolor=FOND, bbox_inches="tight")
print("écrit :", SORTIE)
