"""Wrap the fragment in a full HTML document and screenshot it in both themes."""
import subprocess
import sys
from pathlib import Path

SRC = Path(r"e:\pbl project\report\maharashtra-schools.html")
SCRATCH = Path(r"C:\Users\PRASAD~1\AppData\Local\Temp\claude\e--pbl-project"
               r"\b5db92a2-11e5-4d35-861b-7fc60fe2b24e\scratchpad")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

frag = SRC.read_text(encoding="utf-8")

# (label, window size, px to shift the page up so a lower band lands in frame)
SHOTS = [
    ("top",       "1280,1500", 0),
    ("full",      "1280,13200", 0),
    ("supply",    "1280,1500", 7150),
    ("narrow",    "560,2200",  0),
]

for theme in ("light", "dark"):
    for label, size, offset in SHOTS:
        shift = f"<style>.wrap{{margin-top:-{offset}px}}</style>" if offset else ""
        doc = (f'<!doctype html><html lang="en" data-theme="{theme}"><head>'
               f'<meta charset="utf-8">'
               f'<meta name="viewport" content="width=device-width,initial-scale=1">'
               f'<style>*,*::before,*::after{{box-sizing:border-box}}body{{margin:0}}</style>'
               f'</head><body>{frag}{shift}</body></html>')
        page = SCRATCH / f"preview-{theme}-{label}.html"
        page.write_text(doc, encoding="utf-8")

        shot = SCRATCH / f"shot-{theme}-{label}.png"
        if shot.exists():
            shot.unlink()
        subprocess.run([
            EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--hide-scrollbars", f"--window-size={size}",
            "--virtual-time-budget=3000",
            f"--screenshot={shot}", page.as_uri(),
        ], check=False, capture_output=True, timeout=120)
        print(f"{shot.name}: {'ok' if shot.exists() else 'FAILED'} "
              f"{shot.stat().st_size // 1024 if shot.exists() else 0} KB")
