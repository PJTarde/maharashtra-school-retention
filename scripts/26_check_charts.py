"""Sanity check: every chart container has a renderer, and every renderer a container."""
import re
from pathlib import Path

h = Path(r"e:\pbl project\report\maharashtra-schools.html").read_text(encoding="utf-8")

divs = set(re.findall(r'<div class="chart" id="(c-[\w-]+)"', h))
refs = set(re.findall(r"getElementById\('(c-[\w-]+)'\)", h))

print(f"chart containers ({len(divs)}): {sorted(divs)}")
print(f"renderers        ({len(refs)}): {sorted(refs)}")
print(f"\ncontainer with no renderer: {sorted(divs - refs) or 'none'}")
print(f"renderer with no container: {sorted(refs - divs) or 'none'}")

# other element ids the script writes into
other = set(re.findall(r"getElementById\('([\w-]+)'\)", h)) - refs
present = set(re.findall(r'id="([\w-]+)"', h))
print(f"\nother targets: {sorted(other)}")
print(f"missing from markup: {sorted(other - present) or 'none'}")
print(f"\nsize: {len(h)/1024:.0f} KB")
