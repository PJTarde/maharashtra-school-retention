"""Render PDF pages to PNGs so the pagination can be eyeballed."""
from pathlib import Path

import pypdfium2 as pdfium

PDF = Path(r"e:\pbl project\report\maharashtra-schools.pdf")
OUT = Path(r"C:\Users\PRASAD~1\AppData\Local\Temp\claude\e--pbl-project"
           r"\b5db92a2-11e5-4d35-861b-7fc60fe2b24e\scratchpad")

doc = pdfium.PdfDocument(str(PDF))
print(f"{len(doc)} pages")

# contact sheet: every page side by side, small
from PIL import Image

thumbs = []
for i, page in enumerate(doc):
    img = page.render(scale=1.4).to_pil()
    thumbs.append(img)
    img.save(OUT / f"pdf-p{i+1:02d}.png")

cols, rows = 5, (len(thumbs) + 4) // 5
w, h = thumbs[0].size
sheet = Image.new("RGB", (cols * w, rows * h), "white")
for i, t in enumerate(thumbs):
    sheet.paste(t, ((i % cols) * w, (i // cols) * h))
sheet.thumbnail((2200, 2200))
sheet.save(OUT / "pdf-contact.png")
print("wrote", OUT / "pdf-contact.png", sheet.size)
