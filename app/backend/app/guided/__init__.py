"""Guided knitting in the app: building guides from pattern PDFs in the background, with live progress.

Fork-only module (see FORK.md). The building itself is in app.guide_builder; this module stores jobs and guides,
runs builds in the background, and serves the API under /api/guided.
"""
