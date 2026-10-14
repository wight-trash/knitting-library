"""POST /api/share: a page sent from Safari by an iPhone Shortcut becomes a draft to check."""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.kl.client import KnittingLibrary
from app.main import create_app
from tests.conftest import needs_fixtures
from tests.fakekl import FakeKL

LINK = "https://www.garnstudio.com/pattern.php?id=12759&cid=19"
TOKEN = "a-long-random-share-token-for-tests"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def make_client(settings, token=TOKEN):
    kl = FakeKL()
    s = dataclasses.replace(settings, share_token=token)
    app = create_app(s, kl=KnittingLibrary(s, transport=kl.transport()))
    return TestClient(app), kl


def test_sharing_is_off_without_a_token(settings):
    client, _ = make_client(settings, token="")
    with client:
        r = client.post("/api/share", data={"url": LINK, "html": "x"}, headers=AUTH)
        assert r.status_code == 404
        assert r.json() == {"ok": False, "open": "", "message": "Sharing is switched off on this importer."}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}])
def test_a_wrong_or_missing_key_is_refused(settings, headers):
    client, _ = make_client(settings)
    with client:
        r = client.post("/api/share", data={"url": LINK, "html": "x"}, headers=headers)
        assert r.status_code == 401
        assert r.json()["open"] == ""


def test_other_sites_get_a_plain_message(settings):
    client, _ = make_client(settings)
    with client:
        r = client.post("/api/share", data={"url": "https://example.com/yarn", "html": "<h1>Yarn</h1>"}, headers=AUTH)
        assert r.status_code == 422
        assert "Only DROPS" in r.json()["message"]


def test_an_empty_share_is_refused(settings):
    client, _ = make_client(settings)
    with client:
        r = client.post("/api/share", data={"url": LINK, "html": "  "}, headers=AUTH)
        assert r.status_code == 422 and r.json()["open"] == ""


@needs_fixtures
def test_a_page_that_is_not_the_pattern_is_refused_and_leaves_no_draft(settings):
    client, _ = make_client(settings)
    with client:
        r = client.post("/api/share", data={"url": LINK, "html": "<html><body>Hello</body></html>"}, headers=AUTH)
        assert r.status_code == 422 and r.json()["message"]
        assert not any((settings.data_dir / "drafts").iterdir())


@needs_fixtures
def test_page_and_pdf_make_a_draft_ready_to_check(settings, main_html_bytes, pdf_bytes):
    client, kl = make_client(settings)
    with client:
        r = client.post(
            "/api/share",
            data={"url": LINK, "html": main_html_bytes.decode("utf-8")},
            files={"pdf": ("pattern.pdf", pdf_bytes, "application/pdf")},
            headers=AUTH,  # no X-Requested-With: a Shortcut is not a browser
        )
        body = r.json()
        assert r.status_code == 200, body
        assert body["ok"] and body["message"] == "Pattern received. Opening it to check."
        assert body["open"].startswith("https://knit.example/import/?draft=")
        draft_id = body["open"].rsplit("=", 1)[1]

        d = client.get(f"/api/drafts/{draft_id}").json()
        assert d["status"] == "ready"
        assert d["files"]["main_html"] and d["files"]["pdf"]
        assert d["edits"]["tags"], "tags come from the shared page"

        # From here it is the normal flow: Mary checks it in the browser and adds it.
        r = client.post(f"/api/drafts/{draft_id}/publish", json={}, headers={"X-Requested-With": "knit-import"})
        assert r.status_code == 200


@needs_fixtures
def test_the_page_as_a_file_and_under_import_works_too(settings, main_html_bytes):
    client, _ = make_client(settings)
    with client:
        r = client.post(
            "/import/api/share",
            data={"url": LINK},
            files={"html": ("page.html", main_html_bytes, "text/html")},
            headers=AUTH,
        )
        body = r.json()
        assert r.status_code == 200, body
        assert body["message"] == "The page arrived. Opening it so you can add the PDF."
        d = client.get(f"/api/drafts/{body['open'].rsplit('=', 1)[1]}").json()
        assert d["status"] == "manual" and d["manual"]["code"] == "shared"


def test_the_rest_of_the_api_still_needs_the_header(settings):
    client, _ = make_client(settings)
    with client:
        assert client.post("/api/drafts/manual", headers=AUTH).status_code == 403
