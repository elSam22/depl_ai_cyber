"""Exporte un livrable Markdown (LIVRABLES/TP1_LIVRABLE.md par défaut) en un seul fichier HTML (images intégrées) puis en PDF (via Brave ou Chrome).

Le lecteur reçoit un seul document : les images sont incluses dans le fichier, pas des liens vers des fichiers.
Prérequis : pip install markdown ; un navigateur Chrome/Brave pour le PDF.
Lancement (depuis la racine) : .venv/bin/python outils/exporter_documentation.py [fichier.md]  (par défaut LIVRABLES/TP1_LIVRABLE.md ; TP2 : LIVRABLES/TP2_LIVRABLE.md)
Sorties : <fichier>.html et <fichier>.pdf
"""
import base64
import re
import subprocess
import sys
from pathlib import Path

import markdown

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / (sys.argv[1] if len(sys.argv) > 1 else "LIVRABLES/TP1_LIVRABLE.md")   # ex. : LIVRABLES/TP2_LIVRABLE.md
HTML = SOURCE.with_suffix(".html")
PDF = SOURCE.with_suffix(".pdf")
NAVIGATEURS = ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
               "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]

CSS = """
body{font-family:-apple-system,Helvetica,Arial,sans-serif;font-size:11pt;line-height:1.45;color:#111;max-width:1000px;margin:0 auto;padding:0 12px}
h1{font-size:22pt;border-bottom:2px solid #2a78d6;padding-bottom:6px} h2{font-size:16pt;margin-top:28px;border-bottom:1px solid #ccc;padding-bottom:3px}
h3{font-size:13pt;margin-top:20px} h4{font-size:11.5pt}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:9.5pt} th,td{border:1px solid #bbb;padding:4px 6px;vertical-align:top} th{background:#eef3fa}
code{background:#f3f3f3;padding:1px 3px;border-radius:3px;font-size:9pt} pre{background:#f3f3f3;padding:8px;overflow-x:auto;font-size:8.5pt;white-space:pre-wrap}
img{max-width:100%;height:auto;display:block;margin:10px auto;border:1px solid #ddd} em{color:#444}
h1,h2,h3,h4{page-break-after:avoid;break-after:avoid;break-inside:avoid}
/* Un titre ne reste jamais seul en bas de page : chaque titre « réserve » la place de quelques lignes sous lui ;
   s'il n'y a pas cette place, le titre passe à la page suivante avec la suite. Même règle pour les étiquettes en gras
   qui introduisent un tableau ou une liste (« Interprétation. », « Ce que demande l'énoncé… »). */
h2::after,h3::after,h4::after,p.etiquette::after{content:"";display:block;height:7em;margin-bottom:-7em}
div.bloc{break-inside:avoid;page-break-inside:avoid}
p.etiquette{break-inside:avoid;break-after:avoid;page-break-after:avoid}
img,pre,tr{page-break-inside:avoid;break-inside:avoid} p{orphans:3;widows:3}
"""


def integrer_images(html: str) -> str:
    """Remplace chaque image par son contenu (base64) : le fichier est autonome."""
    def remplacer(m):
        chemin = (SOURCE.parent / m.group(1)).resolve()   # chemin relatif au livrable (../images/...)
        if not chemin.exists():
            sys.exit(f"Image manquante : {chemin}")
        mime = "image/png" if chemin.suffix == ".png" else "image/jpeg"
        return f'src="data:{mime};base64,{base64.b64encode(chemin.read_bytes()).decode()}"'
    return re.sub(r'src="([^"]+\.(?:png|jpg|jpeg))"', remplacer, html)


def aerer_listes(texte: str) -> str:
    """Python-Markdown exige une ligne vide avant une liste (GitHub non) : on l'ajoute pour que les listes s'affichent."""
    lignes, sortie, dans_code = texte.split("\n"), [], False
    for i, ligne in enumerate(lignes):
        if ligne.startswith("```"):
            dans_code = not dans_code
        est_puce = bool(re.match(r"\s*([-*]|\d+\.) ", ligne))
        if (not dans_code and est_puce and i > 0 and sortie and sortie[-1].strip()
                and not re.match(r"\s*([-*]|\d+\.) ", sortie[-1]) and not sortie[-1].lstrip().startswith("|")
                and not sortie[-1].startswith("    ")):
            sortie.append("")
        sortie.append(ligne)
    return "\n".join(sortie)


def main():
    corps = markdown.markdown(aerer_listes(SOURCE.read_text(encoding="utf-8")), extensions=["tables", "fenced_code", "sane_lists"])
    # Étiquettes : paragraphe entièrement en gras, ou court paragraphe qui se termine par « : » avant un tableau/liste
    corps = re.sub(r"<p>(<strong>[^<]{1,120}</strong>)</p>", r'<p class="etiquette">\1</p>', corps)
    corps = re.sub(r"<p>([^<]{0,40}<strong>[^<]{1,160}</strong>[^<]{0,80}:)</p>", r'<p class="etiquette">\1</p>', corps)
    # Une phrase qui présente une image reste sur la même page que l'image
    corps = re.sub(r"<p>((?:(?!</p>).){1,400})</p>\s*(<p><img [^>]*></p>)", r'<div class="bloc"><p>\1</p>\2</div>', corps, flags=re.S)
    # Une phrase courte qui annonce un bloc de code (« Extrait commenté du Dockerfile : ») reste avec lui
    corps = re.sub(r"<p>((?:(?!</p>).){1,200}:)</p>\s*(<pre>(?:(?!</pre>).){1,1500}</pre>)", r'<div class="bloc"><p>\1</p>\2</div>', corps, flags=re.S)
    html = f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>{SOURCE.stem}</title><style>{CSS}</style></head><body>{integrer_images(corps)}</body></html>'
    HTML.write_text(html, encoding="utf-8")
    print("écrit :", HTML)
    nav = next((n for n in NAVIGATEURS if Path(n).exists()), None)
    if not nav:
        print("Aucun navigateur trouvé : ouvrir le fichier HTML produit et faire Imprimer > PDF.")
        return
    subprocess.run([nav, "--headless", "--disable-gpu", "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=60000", f"--print-to-pdf={PDF}", HTML.as_uri()],
                   check=True, capture_output=True, timeout=180)
    print("écrit :", PDF)


if __name__ == "__main__":
    main()
