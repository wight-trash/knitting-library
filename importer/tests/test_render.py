"""Printing a PDF with Chromium, as the container's user does it."""
from __future__ import annotations

import asyncio

from app.drops.pdfinfo import inspect_pdf
from app.drops.render import html_to_pdf
from tests.conftest import needs_chromium


@needs_chromium
def test_prints_even_when_home_is_not_writable(settings, tmp_path, monkeypatch):
    # The importer's user has no home folder. Chromium used to abort at start-up because of that.
    monkeypatch.setenv("HOME", "/nonexistent/importer")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    out = tmp_path / "out.pdf"
    asyncio.run(html_to_pdf("<!doctype html><title>t</title><p>Hello</p>", out, settings))
    assert inspect_pdf(out).pages == 1
