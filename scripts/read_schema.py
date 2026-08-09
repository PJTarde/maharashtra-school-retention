"""Dump text of the UDISE schema / parameter PDFs so enrolment codes can be decoded."""
import sys
import pdfplumber

for path in sys.argv[1:]:
    print("=" * 100)
    print("FILE:", path)
    print("=" * 100)
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            print(f"\n----- page {i} -----")
            print(text)
