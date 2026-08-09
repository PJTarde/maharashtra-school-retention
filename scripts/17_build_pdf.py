"""Render the report to a print-ready PDF.

The report is published as an HTML fragment, so it is wrapped in a full document
here and given print-only CSS: light theme forced, backgrounds preserved (charts
are colour-coded), cards kept off page breaks, and table headers repeated on
every page the table spans.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"e:\pbl project")
SRC = ROOT / "report" / "maharashtra-schools.html"
OUT = ROOT / "report" / "maharashtra-schools.pdf"
SCRATCH = Path(r"C:\Users\PRASAD~1\AppData\Local\Temp\claude\e--pbl-project"
               r"\b5db92a2-11e5-4d35-861b-7fc60fe2b24e\scratchpad")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

PRINT_CSS = """
<style>
@page { size: A4 portrait; margin: 13mm 12mm 14mm; }

html, body { background: #ffffff !important; }
body { font-size: 10.5pt; line-height: 1.5; }

/* the page is a fixed-width canvas in print; let it use the full sheet */
.wrap { max-width: none !important; padding: 0 !important; }

/* charts scroll on screen; on paper they must fit the sheet */
.chart { overflow: visible !important; }
.chart svg { min-width: 0 !important; width: 100% !important; }

/* keep colour: bars and rules carry meaning */
*, *::before, *::after {
  -webkit-print-color-adjust: exact !important;
  print-color-adjust: exact !important;
}

/* pagination */
.card, .finding, .kpis, .caveat, .tablewrap { break-inside: avoid; page-break-inside: avoid; }
section { break-before: auto; }
h1, h2, h3 { break-after: avoid; page-break-after: avoid; }
.card-head { break-after: avoid; }
.masthead { break-after: avoid; }

/* long tables: repeat the header, drop the sticky positioning */
thead { display: table-header-group; }
thead th { position: static !important; }
tbody tr { break-inside: avoid; page-break-inside: avoid; }
.tablewrap { overflow-x: visible !important; }
table { min-width: 0 !important; }
#ptable { font-size: 9pt; }

/* The 36-district table is the one block near a full page. Tighten the rows so
   all 36 fit on one page; the inherited break-inside:avoid then moves it whole
   rather than orphaning a single row. Forcing break-before here would leave the
   preceding page nearly blank. */
#dtable { font-size: 7.9pt; }
#dtable td, #dtable th { padding: 2.5px 6px; }
#dtable caption { padding: 8px 10px 7px; font-size: 8.5pt; }
#dtable .meter-track { width: 46px; height: 4px; }

/* screen-only furniture */
#tip { display: none !important; }
thead th { cursor: default; }

/* tighten the vertical rhythm so the deck is not mostly white space */
section { padding-top: 26px; }
.masthead { padding: 0 0 20px; }
h1 { font-size: 30pt; }
.card { padding: 14px 16px 12px; margin-top: 16px; }
.legend { margin-top: 10px; }
p { margin-bottom: 10px; }
</style>
"""

# a print-only note replacing the "click to sort" affordance
SORT_NOTE = """
<style>
#dtable caption::after { content: " Sorted by infrastructure score, lowest first."; }
</style>
"""


def main() -> None:
    if not SRC.exists():
        sys.exit(f"missing {SRC} - run 11_build_report.py first")

    frag = SRC.read_text(encoding="utf-8")
    # strip the on-screen sorting hint; a PDF cannot be clicked
    frag = frag.replace("Click any heading to sort.", "")

    doc = ('<!doctype html><html lang="en" data-theme="light"><head>'
           '<meta charset="utf-8">'
           '<style>*,*::before,*::after{box-sizing:border-box}body{margin:0}</style>'
           f'</head><body>{frag}{PRINT_CSS}{SORT_NOTE}</body></html>')

    page = SCRATCH / "print.html"
    page.write_text(doc, encoding="utf-8")

    if OUT.exists():
        OUT.unlink()
    res = subprocess.run([
        EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=8000",
        "--no-pdf-header-footer",
        f"--print-to-pdf={OUT}",
        page.as_uri(),
    ], capture_output=True, timeout=300)

    if not OUT.exists():
        print("FAILED\n", res.stdout.decode(errors="replace"),
              res.stderr.decode(errors="replace"))
        sys.exit(1)

    stamp_page_numbers(OUT)
    print(f"wrote {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")


def stamp_page_numbers(pdf: Path) -> None:
    """Chrome's CLI cannot emit a custom footer, so overlay one afterwards."""
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    reader = PdfReader(str(pdf))
    writer = PdfWriter()
    n = len(reader.pages)
    for i, page in enumerate(reader.pages, 1):
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.setFont("Helvetica", 7.5)
        c.setFillGray(0.45)
        c.drawString(34, 20, "Where Maharashtra loses its students · "
                             "UDISE+ 2021-22 to 2025-26")
        c.drawRightString(A4[0] - 34, 20, f"{i} / {n}")
        c.save()
        buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
        writer.add_page(page)

    writer.add_metadata({
        "/Title": "Where Maharashtra Loses Its Students",
        "/Subject": "UDISE+ panel analysis of Maharashtra schools, 2021-22 to 2025-26",
        "/Creator": "scripts/17_build_pdf.py",
    })
    with open(pdf, "wb") as f:
        writer.write(f)


if __name__ == "__main__":
    main()
