"""A yarn picture from a shop link, fetched by the server.

The browser cannot load it itself (the app's own security policy blocks other sites' pictures). Each address,
including every redirect, is checked with upstream's _validate_public_url, as the link import does: public addresses
only. Only real pictures (JPEG, PNG, WebP, GIF, AVIF; never SVG) of at most 20 MB are passed on.
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx
from fastapi import HTTPException

from app.core.foundation import MAX_IMAGE_BYTES, _validate_public_url
from app.stash.ledger import StashError

log = logging.getLogger("knitting.fork.stash")
MAX_BYTES = MAX_IMAGE_BYTES          # 20 MB
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_REDIRECTS = 4
ALLOWED_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif", "image/avif")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KnittingLibrary/1.0)", "Accept": "image/*"}
TRANSPORT: httpx.AsyncBaseTransport | None = None   # tests put a pretend web here

NOT_ALLOWED = "That picture link cannot be used. Copy the address of a picture on a shop's website."


def _sniff(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
        return "image/avif"
    return None


def _check(url: str) -> str:
    try:
        return _validate_public_url(url)
    except HTTPException:
        raise StashError(NOT_ALLOWED, 400) from None


async def fetch_image(url: str) -> tuple[bytes, str]:
    """(bytes, content type) of a public picture. Raises StashError with a plain message."""
    url = (url or "").strip()
    if not url or len(url) > 2000:
        raise StashError(NOT_ALLOWED, 400)
    current = _check(url)
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=TIMEOUT, transport=TRANSPORT) as client:
            for _ in range(MAX_REDIRECTS + 1):
                async with client.stream("GET", current, headers=HEADERS) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location", "")
                        if not location:
                            raise StashError("The shop's website did not send the picture.", 502)
                        current = _check(urljoin(current, location))
                        continue
                    if resp.status_code != 200:
                        raise StashError("The shop's website did not send the picture. Check the link.", 502)
                    declared = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if declared not in ALLOWED_TYPES:
                        raise StashError("That link is not a picture. Copy the address of the picture itself.", 415)
                    length = resp.headers.get("content-length", "")
                    if length.isdigit() and int(length) > MAX_BYTES:
                        raise StashError("That picture is too big (over 20 MB).", 413)
                    chunks, size = [], 0
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise StashError("That picture is too big (over 20 MB).", 413)
                        chunks.append(chunk)
                    data = b"".join(chunks)
                    kind = _sniff(data)
                    if kind is None:
                        raise StashError("That link is not a picture. Copy the address of the picture itself.", 415)
                    return data, kind
    except StashError:
        raise
    except httpx.HTTPError as exc:
        log.info("stash image fetch failed: %s", type(exc).__name__)
        raise StashError("The shop's website could not be reached. Try again later.", 502) from None
    raise StashError("The picture link sent us round in circles. Copy the address of the picture itself.", 400)
