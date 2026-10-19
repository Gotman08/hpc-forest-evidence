"""Check the finished documents, local links, plot reproduction and page bounds."""
from __future__ import annotations

import hashlib
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import fitz
from PIL import Image, ImageDraw

WORK = Path(__file__).resolve().parent
BASE = WORK.parents[1]
OUT = BASE / "outputs/HPC-Forest-Article-R5-R1-R2/edition-r5-r3"
QA = WORK / "verification-r3"
QA.mkdir(exist_ok=False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


dataset = json.loads((OUT / "donnees-r1-r2/comparison.json").read_bytes())
assert sha(OUT / "donnees-r1-r2/comparison.json") == "0c06538d1cc556fadd8cbc7fd7ad3f3238a99f4274765c47b74681c163aa3609"
for item in dataset["series"]:
    assert statistics.mean(item["samples_seconds"]) == item["mean_seconds"]
    assert statistics.stdev(item["samples_seconds"]) == item["sample_sd_seconds"]
    assert [value/item["reference_mean_seconds"] for value in item["samples_seconds"]] == item["normalized_samples"]

links = []
for source in OUT.rglob("*.md"):
    text = source.read_text(encoding="utf8")
    for target in re.findall(r"!?\[[^\]]*\]\(([^\s)]+)\)", text):
        if re.match(r"[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith("#"):
            continue
        path = (source.parent / unquote(target.split("#")[0])).resolve()
        assert path.is_file(), (source.relative_to(OUT), target)
        links.append({"source": source.relative_to(OUT).as_posix(), "target": target})

appendix_html = (OUT / "ANNEXES-TECHNIQUES.html").read_text(encoding="utf8")
new_html = appendix_html[appendix_html.index('<h2 id="l-'):]
assert new_html.count("<table>") == 3 and new_html.count("<tr>") == 102
assert not re.search(r"<p>\|", new_html)
assert "R2 · matrice quinze sujets / quatre modèles MAX" in (OUT / "ARTICLE.md").read_text(encoding="utf8")

reproduced = QA / "reproduced-figures"
completed = subprocess.run([sys.executable, "-B", str(OUT / "donnees-r1-r2/rebuild-figures.py"), "--output", str(reproduced)],
    capture_output=True, text=True, check=False)
assert completed.returncode == 0, completed.stderr
png_proofs = []
for image in reproduced.glob("*.png"):
    original = OUT / "edition-professionnelle/figures/comparaison-r1-r2" / image.name
    assert image.read_bytes() == original.read_bytes(), image.name
    png_proofs.append({"name": image.name, "sha256": sha(image), "reproduced_byte_identically": True})
assert len(png_proofs) == 3

baseline = json.loads((WORK / "BASELINE-MANIFEST.json").read_bytes())
for entry in baseline["preserved_files"]:
    if entry["path"].endswith(".png"):
        assert sha(OUT / entry["path"]) == sha(OUT / "history/r4" / entry["path"]) == entry["sha256"]
for name in ("ARTICLE.pdf", "ANNEXES-TECHNIQUES.pdf"):
    assert sha(OUT / "history/r4" / name) == sha(WORK / "base-r4" / name)

pdfs = {}
rendered = []
for stem in ("ARTICLE", "ANNEXES-TECHNIQUES"):
    doc = fitz.open(OUT / (stem + ".pdf"))
    selected, outside = set(), []
    for i, page in enumerate(doc):
        text = page.get_text()
        if stem == "ARTICLE" and (i in {0, 1, 2} or any(key in text for key in ("3.9. Première", "Figure 8", "Figure 9", "Figure 10", "Tableau 8", "transition R1/R2", "La priorité humaine actuelle"))):
            selected.add(i)
        if stem == "ANNEXES-TECHNIQUES" and i >= 308:
            selected.add(i)
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line["spans"]:
                    x0, y0, x1, y1 = span["bbox"]
                    if x0 < -1 or y0 < -1 or x1 > page.rect.width+1 or y1 > page.rect.height+1:
                        outside.append({"page": i+1, "text": span["text"][:60], "bbox": list(span["bbox"])})
    assert not outside, outside
    thumbs = []
    for i in sorted(selected):
        target = QA / f"{stem}-{i+1:03d}.png"
        doc[i].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(target)
        rendered.append(target.name)
        picture = Image.open(target).convert("RGB"); picture.thumbnail((270, 382))
        thumb = Image.new("RGB", (290, 415), "#e7ecef"); thumb.paste(picture, ((290-picture.width)//2, 22))
        ImageDraw.Draw(thumb).text((8, 2), f"{stem} p. {i+1}", fill="#17354a"); thumbs.append(thumb)
    for start in range(0, len(thumbs), 8):
        sheet = Image.new("RGB", (1160, 830), "white")
        for j, picture in enumerate(thumbs[start:start+8]):
            sheet.paste(picture, ((j%4)*290, (j//4)*415))
        sheet.save(QA / f"{stem}-planche-{start//8+1}.png")
    pdfs[stem] = {"pages": len(doc), "sha256": sha(OUT/(stem+".pdf")), "selected_pages_rendered": [i+1 for i in sorted(selected)], "out_of_page_text_spans": outside}

report = {"schema": "hpc-forest-r5-delivery-local-verification-v1", "dataset_sha256": sha(OUT/"donnees-r1-r2/comparison.json"),
    "pdfs": pdfs, "local_links_checked": len(links), "new_annex_tables": 3, "new_annex_table_rows_including_headers": 102,
    "historical_275_unique_figures_preserved": True, "historical_r4_pdfs_preserved": True,
    "all_six_numeric_series_recalculated": True, "public_plot_rebuild": {"returncode": completed.returncode, "stdout": completed.stdout, "PNG": png_proofs},
    "rendered_pages": rendered, "new_jobs_or_models": 0, "visual_review_completed_by_this_script": False}
(QA / "VERIFICATION.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf8")
print(json.dumps({"report": str(QA/"VERIFICATION.json"), "pdfs": pdfs, "local_links_checked": len(links), "rendered_pages": len(rendered)}))
