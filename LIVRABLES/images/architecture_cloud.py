"""Schéma d'architecture cloud — Digital Social Score (étape 7).
Dessine le schéma avec matplotlib : composants, flux, zones de confiance et supervision (Prometheus, Grafana).
Lancement : .venv/bin/python LIVRABLES/images/architecture_cloud.py LIVRABLES/images/architecture_cloud.png
"""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

import sys
SORTIE = Path(sys.argv[1])

# ── Palette ──────────────────────────────────────────────────────────────────
FOND        = "#f9f9f7"
ENCRE       = "#1a1a18"
GRIS_TEXTE  = "#555550"
VERT        = "#1a7a4a"   # flux sécurisés (HTTPS, secrets)
ROUGE       = "#c0392b"   # HTTP non chiffré
BLEU        = "#2a6db5"   # flux numérotés (requête client)
ORANGE      = "#d4680a"   # supervision (installée)
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
zone(61, 12, 36.5, 43.5, "Cluster GKE Autopilot — Kubernetes géré", JAUNE_FOND)

# ── Composants principaux ─────────────────────────────────────────────────────
# Client
boite(1, 29, 13, 10, "Client",
      ["navigateur,", "curl, app"], fc=GRIS_FOND, ec="#888880")

# Load Balancer
boite(19, 29, 18, 10, "Load Balancer HTTPS",
      ["Ingress Google, IP fixe", "certificat géré, HTTP → HTTPS", "délai 15 s, journaux complets"],
      fc="#ffffff")

# Service K8s
boite(42, 29, 15, 10, "Service dss-api",
      ["ClusterIP :80→8080", "pods prêts uniquement"],
      fc="#ffffff")

# Pods
boite(63, 15, 33, 37, "Pods dss-api  (2 à 5)",
      ["HPA 2 → 5 pods à 70 % CPU · 1 CPU / 2 Go par pod", "non-root (uid 1000), drop ALL, aucun rôle GCP"],
      fc="#fffdf8", ec="#b08030", taille=10)

# Étapes dans le pod
etapes_pod = [
    ("a", "Protection : 429 (débit/IP, clés fausses), 413 (> 40 Ko), 503",  ROUGE),
    ("b", "Vérif. clé X-API-Key (temps constant)  →  401",  ROUGE),
    ("c", "Validation entrée 1–5 000 car.  →  422",          ENCRE),
    ("d", "Anonymisation : regex + spaCy NER  →  8 balises",  VERT),
    ("e", "Nettoyage (+ normalisation anti-évasion, TP2)",     ENCRE),
    ("f", "DistilBERT : 6 probabilités (multi-label)",         BLEU),
    ("g", "Seuils par label → score 0-100 (≤ 3 calculs/pod)",  BLEU),
]
for i, (lettre, texte, coul) in enumerate(etapes_pod):
    yy = 44.2 - 3.3*i
    ax.add_patch(plt.Circle((66.5, yy), 0.9, fc=coul, ec="white", lw=1.2, zorder=5))
    ax.text(66.5, yy, lettre, ha="center", va="center",
            fontsize=7.5, color="white", fontweight="bold", zorder=6)
    etiquette(68, yy, texte, ENCRE, ha="left", taille=7.6)

etiquette(66.5, 21.2, "Sondes /health : startupProbe · readinessProbe · livenessProbe",
          GRIS_TEXTE, ha="left", taille=7.3)
etiquette(66.5, 19.4, "Métriques : port 9090 (non exposé) · système de fichiers en lecture seule",
          GRIS_TEXTE, ha="left", taille=7.3)

# Secret Manager
boite(63, 3, 33, 8.5, "Secret Manager → Secret Kubernetes",
      ["clé API hors code et hors Git", "injectée via variable d'env. API_KEY"],
      fc="#ffffff", ec=VERT, ecw=1.4)

# Artifact Registry + Cloud Build
boite(18, 3, 10.5, 8, "Bucket GCS",
      ["privé : poids", "+ seuils.json"], fc="#ffffff", ec=VERT, ecw=1.4)
boite(32, 3, 11, 8, "Cloud Build",
      ["construit l'image", "(code + modèle)"], fc="#ffffff")
boite(46.5, 3, 12.5, 8, "Artifact Registry",
      ["image Docker", "lecture seule nœuds"], fc="#ffffff")

# Cloud Logging
boite(63, 57.3, 33, 6.4, "Cloud Logging (30 jours)",
      ["API : score · longueur · durée — jamais le texte", "refus : empreinte HMAC de l'IP · load balancer : IP"], fc="#ffffff", ec=VERT)

# Supervision (pointillés)
boite(33, 46, 24, 10, "Supervision (étape 6, installée)",
      ["Prometheus + Grafana + 7 alertes :", "req/s, refus, 5xx, P95, CPU, pods"],
      fc="#fff4e8", ec=ORANGE, ecw=1.6)

# ── Flux numérotés (requête) ──────────────────────────────────────────────────
# 1 Client → LB  (HTTPS)
fleche(14, 34, 19, 34, couleur=VERT, lw=2)
badge(16.5, 34, "1", BLEU)
etiquette(16.5, 41.6, "HTTPS ✓", VERT, taille=7.5, gras=True)
etiquette(16.5, 40.5, "chiffré", VERT, taille=7)

# 2 LB → Service  (HTTP interne)
fleche(37, 34, 42, 34, couleur=ROUGE, lw=2)
badge(39.5, 34, "2", BLEU)
etiquette(39.5, 41.6, "HTTP ✗", ROUGE, taille=7.5, gras=True)
etiquette(39.5, 40.5, "réseau interne", ROUGE, taille=7)

# 3 Service → Pods  (HTTP interne)
fleche(57, 34, 63, 34, couleur=ROUGE, lw=2)
badge(60, 34, "3", BLEU)
etiquette(62, 42.7, "HTTP ✗", ROUGE, ha="right", taille=7.5, gras=True)
etiquette(62, 41.6, "réseau interne", ROUGE, ha="right", taille=7)
etiquette(62, 40.5, "authentification en (b)", ROUGE, ha="right", taille=7)

# 4 Réponse JSON (HTTPS, retour)
ax.plot([64, 15.4, 15.4], [16.5, 16.5, 31], color=VERT, lw=2, solid_capstyle="butt", zorder=4)
fleche(15.4, 31, 14.2, 31, couleur=VERT, lw=2)
badge(36, 16.5, "4", BLEU)
etiquette(36, 14.9, 'réponse HTTPS : {"score": 0-100 arrondi à la dizaine, "toxique": true/false}',
          VERT, taille=7.5)

# ── Flux infrastructure (vert) ────────────────────────────────────────────────
# A : Secret → Pods
fleche(79.5, 11.5, 79.5, 15, couleur=VERT, lw=1.6)
badge(79.5, 13.0, "A", VERT)
etiquette(81, 13.0, "injection secret", VERT, ha="left", taille=7.5)

# B : Artifact Registry → Pods
fleche(59, 8, 63, 13, couleur=VERT, lw=1.6)
badge(61, 10.5, "B", VERT)

# Bucket → Cloud Build → Artifact Registry
fleche(28.5, 7, 32, 7, couleur=VERT, lw=1.4)
fleche(43, 7, 46.5, 7, couleur=ENCRE, lw=1.4)

# D : journaux du load balancer → Cloud Logging
ax.plot([28, 28, 63], [39, 61.5, 61.5], color=VERT, lw=1.4, ls=(0, (4, 3)), zorder=4)
fleche(60, 61.5, 63, 61.5, couleur=VERT, lw=1.4)
badge(28, 58.5, "D", VERT)
etiquette(29.5, 60.3, "journaux du load balancer (IP, chemin, code)", VERT, ha="left", taille=7.2)

# C : Pods → Cloud Logging
fleche(90, 52, 90, 58.5, couleur=VERT, lw=1.6)
badge(90, 55.2, "C", VERT)

# Supervision : métriques des pods (port 9090, interne)
fleche(63, 44, 57, 49, couleur=ORANGE, lw=1.6)
etiquette(50, 44.6, "métriques des pods (port 9090, interne)", ORANGE, ha="center", taille=7.2)

# ── Légende ───────────────────────────────────────────────────────────────────
lx, ly, lw2, lh = 1, 1, 13.4, 26
ax.add_patch(FancyBboxPatch((lx, ly), lw2, lh,
                            boxstyle="round,pad=0.3,rounding_size=0.5",
                            fc="#f4f4f1", ec="#aaaaaa", lw=1, zorder=2))
ax.text(lx + lw2/2, ly + lh - 0.8, "Légende", ha="center", va="top",
        fontsize=9, fontweight="bold", color=ENCRE, zorder=3)

legende_items = [
    ("1–4", "Flux requête/réponse",        BLEU),
    ("a–g", "Étapes dans le pod",           ENCRE),
    ("A",   "Secret → pods",               VERT),
    ("B",   "Image → nœuds",              VERT),
    ("C",   "Journaux de l'API", VERT),
    ("D",   "Journaux du LB", VERT),
    ("▬",   "HTTPS (chiffré)",             VERT),
    ("▬",   "HTTP (réseau interne)",       ROUGE),
    ("▬",   "Supervision (interne)",      ORANGE),
]
for i, (sym, desc, coul) in enumerate(legende_items):
    yy = ly + lh - 2.5 - 2.5*i
    ax.text(lx + 1.2, yy, sym, ha="left", va="center",
            fontsize=8.5, color=coul, fontweight="bold", zorder=3)
    ax.text(lx + 3.5, yy, desc, ha="left", va="center",
            fontsize=7.8, color=ENCRE, zorder=3)

# ── Titre ─────────────────────────────────────────────────────────────────────
ax.text(1, 67.5, "Digital Social Score — Architecture cloud en service (17 novembre 2026)",
        fontsize=14, fontweight="bold", color=ENCRE, va="top")

fig.savefig(SORTIE, dpi=140, facecolor=FOND, bbox_inches="tight")
print("écrit :", SORTIE)
