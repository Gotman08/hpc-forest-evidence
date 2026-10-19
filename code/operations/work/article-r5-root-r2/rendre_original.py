"""Professional A4 PDFs and self-contained HTML from reviewed Markdown."""

import base64
import hashlib
import html
import json
import re
from pathlib import Path

import fitz
import markdown
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    Image,
    KeepTogether,
    LongTable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for name, filename in [
    ("Body", "georgia.ttf"),
    ("BodyBold", "georgiab.ttf"),
    ("BodyItalic", "georgiai.ttf"),
    ("BodyBI", "georgiaz.ttf"),
    ("Sans", "arial.ttf"),
    ("SansBold", "arialbd.ttf"),
    ("Mono", "consola.ttf"),
]:
    pdfmetrics.registerFont(TTFont(name, "C:/Windows/Fonts/" + filename))
pdfmetrics.registerFontFamily(
    "Body", normal="Body", bold="BodyBold", italic="BodyItalic", boldItalic="BodyBI"
)
pdfmetrics.registerFontFamily(
    "Sans", normal="Sans", bold="SansBold", italic="Sans", boldItalic="SansBold"
)
INK = "#17354a"
BLUE = "#006b9e"
GREY = "#526675"
WIDTH = A4[0] - 44 * mm
STYLES = {
    "body": ParagraphStyle(
        "body",
        fontName="Body",
        fontSize=10.1,
        leading=14.4,
        alignment=TA_JUSTIFY,
        spaceAfter=8,
        allowWidows=0,
        allowOrphans=0,
    ),
    "technical": ParagraphStyle(
        "technical",
        fontName="Body",
        fontSize=10.1,
        leading=14.4,
        alignment=TA_LEFT,
        spaceAfter=8,
        allowWidows=0,
        allowOrphans=0,
    ),
    "title": ParagraphStyle(
        "title",
        fontName="SansBold",
        fontSize=24,
        leading=28.5,
        textColor=colors.HexColor(INK),
        spaceBefore=12,
        spaceAfter=14,
        keepWithNext=True,
    ),
    "h2": ParagraphStyle(
        "h2",
        fontName="SansBold",
        fontSize=13.7,
        leading=18,
        textColor=colors.HexColor(INK),
        spaceBefore=17,
        spaceAfter=9,
        keepWithNext=True,
    ),
    "h3": ParagraphStyle(
        "h3",
        fontName="SansBold",
        fontSize=10.4,
        leading=14,
        textColor=colors.HexColor(INK),
        spaceBefore=12,
        spaceAfter=7,
        keepWithNext=True,
    ),
    "caption": ParagraphStyle(
        "caption",
        fontName="Sans",
        fontSize=8.4,
        leading=11.6,
        textColor=colors.HexColor(GREY),
        spaceBefore=5,
        spaceAfter=13,
    ),
    "tablecaption": ParagraphStyle(
        "tablecaption",
        fontName="Sans",
        fontSize=8.7,
        leading=12,
        textColor=colors.HexColor(INK),
        spaceBefore=6,
        spaceAfter=6,
        keepWithNext=True,
    ),
    "cell": ParagraphStyle(
        "cell",
        fontName="Sans",
        fontSize=7.6,
        leading=10,
        spaceAfter=0,
        wordWrap="LTR",
        splitLongWords=True,
    ),
    "header": ParagraphStyle(
        "header",
        fontName="SansBold",
        fontSize=7.8,
        leading=10.3,
        textColor=colors.white,
        spaceAfter=0,
        splitLongWords=True,
    ),
    "small": ParagraphStyle(
        "small",
        fontName="Sans",
        fontSize=8.8,
        leading=12.5,
        textColor=colors.HexColor(GREY),
        spaceAfter=9,
    ),
    "author": ParagraphStyle(
        "author",
        fontName="SansBold",
        fontSize=11.2,
        leading=15,
        spaceAfter=8,
        textColor=colors.HexColor(INK),
    ),
    "reference": ParagraphStyle(
        "reference",
        fontName="Body",
        fontSize=8.8,
        leading=12,
        spaceAfter=8,
        splitLongWords=True,
    ),
}


def inline(text):
    t = html.escape(text)
    t = re.sub(
        r"[₀₁₂₃₄₅₆₇₈₉ₚ]+",
        lambda m: (
            "<sub>"
            + m[0].translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉ₚ", "0123456789p"))
            + "</sub>"
        ),
        t,
    )
    t = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: (
            '<a color="'
            + BLUE
            + '" href="'
            + html.escape(html.unescape(m[2]), quote=True)
            + '">'
            + m[1]
            + "</a>"
        ),
        t,
    )
    t = re.sub(r"`([^`]+)`", r'<font name="Mono" size="7.5">\1</font>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", t)
    return t


class Document(BaseDocTemplate):
    def __init__(self, path, supplement=False):
        super().__init__(
            str(path),
            pagesize=A4,
            leftMargin=22 * mm,
            rightMargin=22 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            title="HPC-Forest — "
            + (
                "Annexes techniques"
                if supplement
                else "Évaluer l’optimisation de code par des modèles de langage"
            ),
            author="Nicolas Marano; Romain Despoullain",
            subject="Recherche expérimentale, preuves et analyse de performance",
            lang="fr-FR",
            pageCompression=1,
        )
        self.supplement = supplement
        self.section = ""
        self.heading_counter = 0
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="content",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(
            PageTemplate(id="article", frames=frame, onPage=self.decor)
        )

    def beforeDocument(self):
        self.heading_counter = 0
        self.section = ""

    def decor(self, canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#b8cbd7"))
        canvas.setLineWidth(0.45)
        canvas.line(22 * mm, 15.5 * mm, A4[0] - 22 * mm, 15.5 * mm)
        canvas.setFont("Sans", 7.5)
        canvas.setFillColor(colors.HexColor(GREY))
        canvas.drawString(
            22 * mm,
            11.2 * mm,
            "HPC-FOREST  /  "
            + ("ANNEXES TECHNIQUES" if self.supplement else "ARTICLE DE RECHERCHE"),
        )
        canvas.drawRightString(
            A4[0] - 22 * mm, 11.2 * mm, f"19 octobre 2026  ·  {doc.page}"
        )
        if doc.page > 1:
            canvas.setFont("Sans", 7.3)
            canvas.drawString(
                22 * mm, A4[1] - 12 * mm, "Nicolas Marano · Romain Despoullain"
            )
        canvas.restoreState()

    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and getattr(f, "heading_level", None) is not None:
            level = f.heading_level
            self.heading_counter += 1
            key = f"section-{self.heading_counter}"
            text = f.getPlainText()
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=level > 0)
            if level == 0:
                self.notify("TOCEntry", (0, text, self.page, key))
                self.section = text


def make_table(rows):
    count = len(rows[0])
    # Preserve enough space for numeric cells and long provenance strings.
    if count == 2:
        first_max = max((len(r[0]) for r in rows), default=0)
        weights = [0.31, 0.69] if first_max < 60 else [0.53, 0.47]
    elif count == 3:
        weights = [0.26, 0.30, 0.44]
    elif count == 4:
        weights = [0.34, 0.25, 0.25, 0.16]
    elif count == 5:
        weights = [0.28, 0.13, 0.13, 0.13, 0.33]
    elif count == 6:
        weights = [0.26, 0.18, 0.18, 0.12, 0.12, 0.14]
    elif count == 7:
        weights = [0.10, 0.23, 0.23, 0.10, 0.09, 0.11, 0.14]
    else:
        weights = [1 / count] * count
    if count == 6 and rows[0][0] == "Identité":
        weights = [0.30, 0.14, 0.14, 0.14, 0.14, 0.14]
    if count == 4 and rows[0][0] == "Ensemble natif clos":
        weights = [0.37, 0.11, 0.30, 0.22]
    if count == 7 and rows[0][0] == "Campagne / effort":
        weights = [0.36, 0.15, 0.10, 0.10, 0.10, 0.10, 0.09]
    if count == 5 and rows[0][0] == "Modèle / sujet":
        weights = [0.27, 0.10, 0.13, 0.40, 0.10]
    cells = []
    for i, row in enumerate(rows):
        assert len(row) == count, (row, rows[0])
        cells.append(
            [Paragraph(inline(x), STYLES["header" if i == 0 else "cell"]) for x in row]
        )
    table = LongTable(
        cells,
        colWidths=[WIDTH * w / sum(weights) for w in weights],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(INK)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f1f5f7")],
                ),
                ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.HexColor("#9ab2c2")),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def pdf(path, supplement):
    lines = path.read_text(encoding="utf-8").splitlines()
    flow = []
    i = 0
    references = False
    toc_added = False
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        image = re.fullmatch(r"!\[([^\]]+)\]\(([^)]+)\)", line)
        if image:
            source = ROOT / image[2]
            pic = Image(str(source))
            factor = WIDTH / pic.imageWidth
            maximum = (
                185 * mm if "/arbres/" in str(source).replace("\\", "/") else 112 * mm
            )
            factor = min(factor, maximum / pic.imageHeight)
            pic.drawWidth = pic.imageWidth * factor
            pic.drawHeight = pic.imageHeight * factor
            caption = Paragraph(inline(image[1]), STYLES["caption"])
            flow.append(KeepTogether([Spacer(1, 5), pic, caption]))
            i += 1
            continue
        if line.startswith("|"):
            rr = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cc = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cc):
                    rr.append(cc)
                i += 1
            flow.extend([make_table(rr), Spacer(1, 10)])
            continue
        if line.startswith("#"):
            depth = len(line) - len(line.lstrip("#"))
            text = line.lstrip("#").strip()
            if depth == 1:
                flow.append(
                    Paragraph("HPC-FOREST  /  ÉTUDE EXPÉRIMENTALE", STYLES["small"])
                )
                flow.append(Paragraph(inline(text), STYLES["title"]))
            else:
                if supplement and not toc_added:
                    flow.append(PageBreak())
                    flow.append(Paragraph("Sommaire des annexes", STYLES["h2"]))
                    toc = TableOfContents()
                    toc.levelStyles = [
                        ParagraphStyle(
                            "toc0",
                            fontName="Sans",
                            fontSize=10,
                            leading=16,
                            leftIndent=0,
                            firstLineIndent=0,
                            spaceBefore=8,
                        )
                    ]
                    flow.extend([toc, PageBreak()])
                    toc_added = True
                elif supplement and depth == 2:
                    flow.append(PageBreak())
                if depth == 3:
                    # A conditional break between consecutive parent/child
                    # headings would strand the parent on the previous page.
                    if flow and isinstance(flow[-1], Paragraph) and getattr(flow[-1], "heading_level", None) == 0:
                        flow.insert(len(flow) - 1, CondPageBreak(63 * mm))
                    else:
                        flow.append(CondPageBreak(48 * mm))
                heading = Paragraph(inline(text), STYLES["h2" if depth == 2 else "h3"])
                heading.heading_level = 0 if depth == 2 else 1
                flow.append(heading)
            references = text == "Références"
            i += 1
            continue
        para = [line]
        i += 1
        while (
            i < len(lines)
            and lines[i].strip()
            and not lines[i].strip().startswith(("#", "|", "!["))
        ):
            para.append(lines[i].strip())
            i += 1
        text = " ".join(para)
        if text.startswith("**Nicolas"):
            style = "author"
        elif text.startswith("*Tableau"):
            style = "tablecaption"
        elif text.startswith(
            (
                "Rapport de recherche",
                "Complément de l’article",
                "*Recherche arborescente",
            )
        ):
            style = "small"
        elif references:
            style = "reference"
        elif text.startswith(
            (
                "Racine complète",
                "Registre SHA-256",
                "Le programme retenu",
                "Cas du tableau",
            )
        ):
            style = "technical"
        else:
            style = "body"
        flow.append(Paragraph(inline(text), STYLES[style]))
    doc = Document(path.with_suffix(".pdf"), supplement)
    if supplement:
        doc.multiBuild(flow)
    else:
        doc.build(flow)


CSS = """@page{size:A4;margin:22mm}*{box-sizing:border-box}body{font-family:Georgia,serif;color:#17354a;background:#f3f6f8;margin:0;font-size:17px;line-height:1.65}main{max-width:1020px;margin:35px auto;padding:58px 70px;background:white;box-shadow:0 8px 35px #15354a12}h1,h2,h3,nav,figcaption{font-family:Arial,sans-serif}h1{font-size:2.2rem;line-height:1.16;letter-spacing:-.025em}h2{border-top:1px solid #d6e1e8;padding-top:23px;margin-top:40px}h3{font-size:1.13rem;margin-top:26px}a{color:#006b9e;text-decoration:none}a:hover{text-decoration:underline}p{text-align:justify}img{display:block;width:100%;height:auto;margin:20px auto}table{border-collapse:collapse;width:100%;font:12px/1.5 Arial,sans-serif;margin:15px 0 24px}thead{background:#17354a;color:white}td,th{padding:8px;border-bottom:1px solid #dbe4eb;text-align:left;vertical-align:top;overflow-wrap:anywhere}tbody tr:nth-child(even){background:#f1f5f7}code{font:11px Consolas,monospace;overflow-wrap:anywhere}nav{font-size:13px;background:#f1f5f7;padding:16px}figure{break-inside:avoid}figcaption{font-size:13px;line-height:1.55;color:#526675;margin-bottom:25px}.toc ul{list-style:none;padding-left:15px}.toc li{margin:4px 0}.badge{font:12px Arial,sans-serif;letter-spacing:.1em;color:#526675}@media(max-width:700px){main{padding:22px;margin:0}h1{font-size:1.8rem}body{font-size:15px}table{font-size:10px}}@media print{body{background:white}main{box-shadow:none;margin:0;padding:0}nav{display:none}h2,h3{break-after:avoid}img{max-height:220mm;object-fit:contain}a{color:inherit}}"""


def web(path):
    text = path.read_text(encoding="utf-8")
    rendered = markdown.markdown(
        text,
        extensions=["tables", "toc", "sane_lists"],
        extension_configs={"toc": {"toc_depth": "2-2"}},
    )

    def embed(m):
        src = ROOT / html.unescape(m[1])
        data = base64.b64encode(src.read_bytes()).decode("ascii")
        return 'src="data:image/png;base64,' + data + '"'

    rendered = re.sub(r'src="([^"]+\.png)"', embed, rendered)
    # Each figure is associated with its full caption, visible at normal zoom.
    rendered = re.sub(
        r'<p><img alt="([^"]*)" src="([^"]+)"\s*/?></p>',
        lambda m: (
            '<figure><img alt="'
            + m[1]
            + '" src="'
            + m[2]
            + '"><figcaption>'
            + m[1]
            + "</figcaption></figure>"
        ),
        rendered,
    )
    if "ANNEXES" in path.name:
        toc = markdown.Markdown(
            extensions=["toc"], extension_configs={"toc": {"toc_depth": "2-2"}}
        )
        toc.convert(text)
        navigation = toc.toc
    else:
        navigation = '<a href="ANNEXES-TECHNIQUES.html">Annexes techniques</a> · <a href="ARTICLE.pdf">Version PDF</a>'
    page = (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="author" content="Nicolas Marano; Romain Despoullain"><title>HPC-Forest — '
        + ("Annexes techniques" if "ANNEXES" in path.name else "Article de recherche")
        + "</title><style>"
        + CSS
        + '</style></head><body><main><div class="badge">HPC-FOREST / RECHERCHE EXPÉRIMENTALE</div><nav>'
        + navigation
        + "</nav>"
        + rendered
        + "</main></body></html>"
    )
    path.with_suffix(".html").write_text(page, encoding="utf-8")


def main():
    metadata = []
    for name in ("ARTICLE", "ANNEXES-TECHNIQUES"):
        path = ROOT / (name + ".md")
        pdf(path, name != "ARTICLE")
        web(path)
        doc = fitz.open(path.with_suffix(".pdf"))
        metadata.append(
            {
                "name": name,
                "pages": len(doc),
                "pdf_sha256": hashlib.sha256(
                    path.with_suffix(".pdf").read_bytes()
                ).hexdigest(),
                "figures": len(re.findall(r"!\[", path.read_text(encoding="utf-8"))),
            }
        )
        print(json.dumps(metadata[-1]))
    (HERE / "rendu-manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
