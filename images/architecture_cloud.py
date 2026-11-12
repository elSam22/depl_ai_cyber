"""Dessine le schéma d'architecture cloud de l'API Digital Social Score (étape 7) -> images/architecture_cloud.png.

Le schéma reprend ce que contiennent les scripts et manifestes de la branche Enzo (api/deploy, api/k8s, api/Dockerfile).
Ce qui n'existe pas encore (supervision) est en pointillés.

Lancement (depuis la racine) : .venv/bin/python images/architecture_cloud.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

SORTIE = Path(__file__).resolve().parent / "architecture_cloud.png"
ENCRE, ENCRE_2, FOND = "#0b0b0b", "#52514e", "#fcfcfb"
BLEU, ORANGE, VERT, GRIS = "#2a78d6", "#eb6834", "#1f8f5f", "#d9d8d3"

fig, ax = plt.subplots(figsize=(15, 9), facecolor=FOND)
ax.set_xlim(0, 100)
ax.set_ylim(0, 66)
ax.axis("off")


def boite(x, y, w, h, titre, lignes=(), fc="#ffffff", ec=ENCRE_2, pointille=False, taille=10, gras=True):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.8", fc=fc, ec=ec, lw=1.6,
                                ls=(0, (5, 3)) if pointille else "-"))
    ax.text(x + w / 2, y + h - 1.4, titre, ha="center", va="top", fontsize=taille,
            fontweight="bold" if gras else "normal", color=ENCRE)
    for i, ligne in enumerate(lignes):
        ax.text(x + w / 2, y + h - 3.6 - 1.75 * i, ligne, ha="center", va="top", fontsize=8.5, color=ENCRE_2)


def zone(x, y, w, h, titre, fc):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=1.2", fc=fc, ec=GRIS, lw=1.4))
    ax.text(x + 1.2, y + h - 0.9, titre, ha="left", va="top", fontsize=9.5, color=ENCRE_2, fontstyle="italic")


def fleche(x1, y1, x2, y2, couleur=ENCRE, pointille=False, texte=None, tx=None, ty=None):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=couleur, lw=1.8, ls=(0, (4, 3)) if pointille else "-",
                                shrinkA=0, shrinkB=0))
    if texte:
        ax.text(tx if tx is not None else (x1 + x2) / 2, ty if ty is not None else (y1 + y2) / 2 + 1.1, texte,
                ha="center", va="bottom", fontsize=8.5, color=couleur, fontweight="bold")


def numero(x, y, n, couleur=BLEU):
    ax.add_patch(plt.Circle((x, y), 1.25, fc=couleur, ec="white", lw=1.5, zorder=5))
    ax.text(x, y, str(n), ha="center", va="center", fontsize=9, color="white", fontweight="bold", zorder=6)


# ---- zones
zone(18.5, 1.5, 80.5, 59.5, "Google Cloud : région europe-west9 (Paris), données dans l'UE", "#f4f7fc")
zone(64.5, 14.5, 33.5, 38, "Cluster GKE Autopilot (Kubernetes)", "#fff6ef")

# ---- flux principal
boite(1.5, 27, 13.5, 11, "Client", ["front, curl,", "application"])
boite(22, 27, 17.5, 11, "Load balancer HTTPS", ["Ingress Google", "IP fixe, certificat géré", "HTTP redirigé vers HTTPS"])
boite(44, 27, 15, 11, "Service dss-api", ["ClusterIP, port 80", "vers 8080 des pods", "pods prêts seulement"])
boite(66, 17, 30.5, 32.5, "Pods dss-api : 2 à 5", ["autoscaler à 70 % de CPU", "utilisateur non-root, privilèges retirés"], fc="#ffffff")

etapes = ["a  clé X-API-Key vérifiée (401 sinon)", "b  validation : 1 à 5 000 caractères (422 sinon)",
          "c  anonymisation : regex + NER spaCy", "d  nettoyage : minuscules, emojis, ponctuation",
          "e  DistilBERT : 6 probabilités", "f  seuils par label, score 0 à 100"]
for i, e in enumerate(etapes):
    ax.text(68, 40.2 - 2.9 * i, e, ha="left", va="top", fontsize=9, color=ENCRE)
ax.text(68, 22.2, "Sondes /health : démarrage, prêt, vivant", ha="left", va="top", fontsize=8.5, color=ENCRE_2)

fleche(15, 32.5, 22, 32.5)
fleche(39.5, 32.5, 44, 32.5)
fleche(59, 32.5, 66, 32.5)
numero(18.5, 35.0, 1); numero(41.8, 35.0, 2); numero(62.5, 35.0, 3)
ax.text(18.5, 39.6, "HTTPS (chiffré)", ha="center", va="bottom", fontsize=8.5, color=BLEU, fontweight="bold")

# ---- chaîne de construction
boite(22, 5, 14, 8, "Cloud Build", ["construit l'image", "sans rien installer en local"])
boite(41, 4, 17, 10, "Artifact Registry", ["image : code + modèle", "(aucun téléchargement", "au démarrage)"])
fleche(36, 9, 41, 9)
fleche(58, 10, 66, 20, couleur=VERT)
ax.text(60.0, 17.2, "B", fontsize=9, color=VERT, fontweight="bold", ha="right")
ax.text(30, 3.3, "livraison : deploy_gke.sh", ha="center", fontsize=8.5, color=ENCRE_2)

# ---- secret
boite(66, 5, 30.5, 8, "Secret Manager, puis Secret Kubernetes", ["clé API jamais dans le code ni dans Git", "injectée dans la variable API_KEY"])
fleche(81, 13, 81, 17, couleur=VERT)
ax.text(79.8, 14.4, "A", fontsize=9, color=VERT, fontweight="bold", ha="right")

# ---- journaux et supervision
boite(66, 53, 30.5, 6, "Cloud Logging", ["score, longueur, durée : jamais le texte"], taille=10)
fleche(92, 49.5, 92, 53, couleur=VERT)
ax.text(90.8, 50.6, "C", fontsize=9, color=VERT, fontweight="bold", ha="right")
boite(40, 47, 22, 9, "Supervision (à faire, étape 6)", ["Prometheus et Grafana :", "requêtes/s, erreurs, latence"], pointille=True,
      ec=ORANGE)
fleche(66, 46, 62, 49, couleur=ORANGE, pointille=True)

# ---- retour de la réponse (JSON) : des pods vers le client
ax.plot([66, 8], [24.5, 24.5], color=ENCRE, lw=1.6, solid_capstyle="butt")
fleche(8, 24.5, 8, 27)
numero(37, 24.5, 4, couleur=ENCRE)
ax.text(37, 22.9, "réponse JSON : score, labels, seuils, labels détectés", ha="center", va="top", fontsize=8.5, color=ENCRE)

ax.text(1.5, 65.5, "Digital Social Score : architecture cloud", fontsize=14, fontweight="bold", color=ENCRE, va="top")
ax.text(1.5, 15, "Lecture\n1 à 4 : trajet d'une requête\na à f : étapes dans le pod\nA : secret\nB : image\nC : journaux\nPointillés : pas encore en place", fontsize=9, color=ENCRE_2, va="top")

fig.savefig(SORTIE, dpi=140, facecolor=FOND, bbox_inches="tight")
print("écrit :", SORTIE)
