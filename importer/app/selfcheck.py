"""Checks that the PDF tools work inside the image: Chromium prints a page, poppler reads it back.

    python -m app.selfcheck

Prints one line per check and exits non-zero if any fails. CI runs it on every importer image before
publishing it. It needs no network, no data and no Knitting Library.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from app.config import load_settings
from app.drops.pdfinfo import inspect_pdf, render_page_jpeg
from app.drops.render import html_to_pdf
from app.drops.text import pdf_to_text

PAGE = "<!doctype html><meta charset=utf-8><title>Self check</title><h1>Knit Import self check</h1><p>Strikkefasthet: 21 masker.</p>"


def main() -> int:
    settings = load_settings()
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "check.pdf"
        try:
            asyncio.run(html_to_pdf(PAGE, pdf, settings))
            print(f"ok    Chromium printed a PDF ({pdf.stat().st_size} bytes) using {settings.chromium_path}")
        except Exception as exc:
            print(f"FAIL  Chromium could not print a PDF: {exc!r}")
            return 1

        facts = inspect_pdf(pdf)
        text = pdf_to_text(pdf)
        if facts.ok and facts.pages == 1 and "Strikkefasthet" in text:
            print("ok    poppler read the PDF: 1 page, text intact")
        else:
            print(f"FAIL  poppler could not read the PDF: pages={facts.pages} text={text[:60]!r} {facts.error}")
            ok = False

        if render_page_jpeg(pdf, 1, Path(tmp) / "p1.jpg"):
            print("ok    poppler drew a page preview")
        else:
            print("FAIL  poppler could not draw a page preview")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

