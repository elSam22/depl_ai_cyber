"""Contrôle de mise en page d'un PDF exporté : aucun titre (ni étiquette en gras) ne doit finir une page.

Lancement (macOS, depuis la racine) : python3 outils/verifier_pdf.py livrables/TP1_LIVRABLE.md
Lit le texte de chaque page du PDF (PDFKit de macOS, via osascript) et compare la dernière ligne de chaque page
aux titres et étiquettes du Markdown source. Code de sortie 1 s'il y a un titre orphelin.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

source = Path(sys.argv[1])
pdf = source.with_suffix(".pdf").resolve()
script = ('ObjC.import("PDFKit"); var d=$.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath("%s")); var p=[];'
          'for (var i=0;i<d.pageCount;i++){p.push(ObjC.unwrap(d.pageAtIndex(i).string))} JSON.stringify(p)') % pdf
pages = json.loads(subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True,
                                  check=True).stdout)


def norme(t: str) -> str:
    """Texte réduit à l'essentiel (sans marques Markdown, en minuscules, espaces simplifiés) pour comparer un titre du
    Markdown à une ligne extraite du PDF."""
    t = re.sub(r"[*`_#>]|\[|\]\([^)]*\)", "", t)
    return re.sub(r"\s+", " ", t).strip().lower()


titres = set()      # titres (#) et étiquettes en gras du Markdown : ce qu'il ne faut pas trouver en bas de page
dans_code = False
for ligne in source.read_text(encoding="utf-8").splitlines():
    if ligne.startswith("```"):      # dans un bloc de code, un « # » est un commentaire, pas un titre
        dans_code = not dans_code
    if dans_code:
        continue
    if re.match(r"^#{1,4} ", ligne) or re.fullmatch(r"\*\*[^*]{1,160}\*\*[^|]{0,80}:?", ligne.strip()):
        titres.add(norme(ligne))

# Pour chaque page sauf la dernière : sa dernière ligne de texte (hors numéro de page) est-elle un titre ?
orphelins = []
for n, texte in enumerate(pages[:-1], start=1):
    lignes = [norme(x) for x in texte.splitlines() if x.strip() and not re.fullmatch(r"\d+", x.strip())]
    if lignes and lignes[-1] in titres:
        orphelins.append((n, lignes[-1]))
print(f"{pdf.name} : {len(pages)} pages, {len(orphelins)} titre(s) en fin de page")
for n, t in orphelins:
    print(f"  page {n} : {t[:90]}")
sys.exit(1 if orphelins else 0)
