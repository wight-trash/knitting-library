"""Smoke test for a freshly built Knitting Library container. Standard library only.

    python3 .github/scripts/kl-smoke.py http://127.0.0.1:18080

Waits for the app, creates the first admin (bcrypt), uploads a one-page PDF (multipart, Pillow),
and waits for the page picture (poppler). Exits non-zero on the first failure.
Run it against a fresh, empty instance: it needs the "create the first admin" step to be open.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:18080"


def tiny_pdf() -> bytes:
    """A valid one-page PDF with a line of text, with a correct cross-reference table."""
    stream = b"BT /F1 24 Tf 72 720 Td (Smoke test) Tj ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def call(method: str, path: str, *, token: str = "", body: bytes | None = None, ctype: str = "") -> tuple[int, dict | str]:
    req = urllib.request.Request(BASE + path, data=body, method=method)
    if token:
        req.add_header("X-Session-Token", token)
    if ctype:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw, status, rtype = r.read(), r.status, r.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        raw, status, rtype = e.read(), e.code, e.headers.get("content-type", "")
    if "json" in rtype:
        return status, json.loads(raw or b"{}")
    return status, raw.decode("utf-8", "replace")


def fail(msg: str) -> None:
    print(f"FAIL  {msg}")
    sys.exit(1)


def main() -> None:
    for _ in range(60):
        try:
            status, data = call("GET", "/api/setup/status")
            if status == 200:
                break
        except OSError:
            pass
        time.sleep(1)
    else:
        fail("the app did not answer within 60 seconds")
    print("ok    the app answers")
    if not (isinstance(data, dict) and data.get("setup_required")):
        fail(f"expected a fresh instance, got {data!r}")

    status, page = call("GET", "/")
    if status != 200 or "<div id=\"root\"" not in str(page) and "id=root" not in str(page):
        fail(f"the web page did not load (status {status})")
    print("ok    the web page loads")

    pw = "smoke-" + uuid.uuid4().hex
    status, data = call("POST", "/api/setup/admin", body=json.dumps({"username": "smoke", "password": pw}).encode(), ctype="application/json")
    token = data.get("token") if isinstance(data, dict) else None
    if status != 200 or not token:
        fail(f"could not create the first admin: {status} {data!r}")
    status, data = call("POST", "/api/auth/login", body=json.dumps({"username": "smoke", "password": pw}).encode(), ctype="application/json")
    if status != 200 or not (isinstance(data, dict) and data.get("token")):
        fail(f"could not sign in: {status} {data!r}")
    print("ok    admin created and signed in (bcrypt)")

    boundary = uuid.uuid4().hex
    parts = [
        (b'Content-Disposition: form-data; name="title"', b"Smoke test"),
        (b'Content-Disposition: form-data; name="description"', b""),
        (b'Content-Disposition: form-data; name="categories"', b"Test"),
        (b'Content-Disposition: form-data; name="tags"', b"smoke"),
        (b'Content-Disposition: form-data; name="files"; filename="smoke.pdf"\r\nContent-Type: application/pdf', tiny_pdf()),
    ]
    body = b"".join(b"--%s\r\n%s\r\n\r\n%s\r\n" % (boundary.encode(), head, value) for head, value in parts) + b"--%s--\r\n" % boundary.encode()
    status, data = call("POST", "/api/recipes", token=token, body=body, ctype=f"multipart/form-data; boundary={boundary}")
    recipe_id = data.get("id") if isinstance(data, dict) else None
    if status not in (200, 201) or not recipe_id:
        fail(f"could not add a PDF recipe: {status} {data!r}")
    print(f"ok    PDF recipe added ({recipe_id})")

    for _ in range(30):
        status, data = call("GET", f"/api/recipes/{recipe_id}/pdf-pages", token=token)
        pages = data.get("pages", data) if isinstance(data, dict) else data
        if status == 200 and isinstance(pages, list) and pages:
            print(f"ok    page picture made ({len(pages)} page)")
            break
        time.sleep(1)
    else:
        fail(f"no page picture after 30 seconds: {status} {data!r}")

    status, data = call("GET", f"/api/recipes/{recipe_id}/thumbnail", token=token)
    if status != 200:
        fail(f"no thumbnail: {status}")
    print("ok    thumbnail made")


if __name__ == "__main__":
    main()
