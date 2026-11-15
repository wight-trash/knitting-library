"""Signing in with Keycloak (FORK.md "Signing in with Keycloak"), end to end through the API.

Keycloak is replaced by a fake: discovery, the token exchange and the signing key are patched, and ID tokens
are real RS256 tokens signed with a key made here, so the checks on signature, issuer, audience, expiry and
nonce all run for real.

Needs KNITTING_DATA_DIR, KNITTING_LOG_DIR and KNITTING_STATIC_DIR set to temporary folders, as the other API tests do.
"""
import os
import time
import unittest
import uuid
from unittest import mock
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

ISSUER = "https://auth.example.test/realms/test"
PUBLIC = "https://knit.example.test"
ENV = {
    "OIDC_ISSUER": ISSUER,
    "OIDC_CLIENT_ID": "knitting",
    "OIDC_CLIENT_SECRET": "s3cret",
    "OIDC_PUBLIC_URL": PUBLIC,
}
DOC = {
    "issuer": ISSUER,
    "authorization_endpoint": f"{ISSUER}/protocol/openid-connect/auth",
    "token_endpoint": f"{ISSUER}/protocol/openid-connect/token",
    "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs",
}
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class OidcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main
        from app.core.foundation import get_db

        cls.get_db = staticmethod(get_db)
        cls.client = TestClient(main.app, base_url=PUBLIC)
        cls.client.__enter__()
        status = cls.client.get("/api/setup/status").json()
        if status.get("setup_required"):
            tok = cls.client.post("/api/setup/admin", json={"username": "guidetest", "password": "guided-test-password-1"}).json()["token"]
        else:  # another test created the admin already
            tok = cls.client.post("/api/auth/login", json={"username": "guidetest", "password": "guided-test-password-1"}).json().get("token")
        cls.h = {"X-Session-Token": tok}
        cls.client.cookies.clear()
        cls.suffix = uuid.uuid4().hex[:6]
        cls.mary = f"mary{cls.suffix}"
        cls.importer = f"importer{cls.suffix}"
        for name in (cls.mary, cls.importer):
            r = cls.client.post("/api/admin/users", headers=cls.h,
                                json={"username": name, "password": "unused-password-123"})
            assert r.status_code == 200, r.text

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        from app.oidc import service
        self.service = service
        self.client.cookies.clear()
        self.env = mock.patch.dict(os.environ, {**ENV, "OIDC_PASSWORD_LOGIN_USERS": self.importer})
        self.env.start()
        self.claims_override = {}
        patches = [
            mock.patch.object(service, "_discovery", return_value=DOC),
            mock.patch.object(service, "_signing_key", return_value=KEY.public_key()),
            mock.patch.object(service, "_exchange_code", side_effect=self._fake_exchange),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.env.stop)

    # The fake Keycloak: answers the code exchange with an ID token for whoever self.person is.
    person = {"sub": "sub-mary", "preferred_username": "mary"}

    def _fake_exchange(self, cfg, doc, code, verifier):
        self.assertTrue(verifier)
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "knitting", "iat": now, "exp": now + 300,
                  "nonce": self.nonce, **self.person, **self.claims_override}
        return {"id_token": jwt.encode(claims, KEY, algorithm="RS256"), "access_token": "x"}

    def _sign_in(self, person: dict):
        """Run the browser side: start, then come back to the callback. Returns the final response."""
        self.person = person
        r = self.client.get("/api/auth/oidc/start", follow_redirects=False)
        self.assertEqual(r.status_code, 303, r.text)
        q = parse_qs(urlparse(r.headers["location"]).query)
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["redirect_uri"], [PUBLIC + "/api/auth/oidc/callback"])
        conn = self.get_db()
        self.nonce = conn.execute("SELECT nonce FROM oidc_pending WHERE state=?", (q["state"][0],)).fetchone()["nonce"]
        conn.close()
        self.assertEqual(q["nonce"], [self.nonce])
        return self.client.get("/api/auth/oidc/callback", params={"code": "abc", "state": q["state"][0]},
                               follow_redirects=False)

    def _me(self):
        return self.client.get("/api/auth/me")

    def _unlink(self, name):
        self.client.cookies.clear()
        self.client.delete(f"/api/auth/oidc/links/{name}", headers=self.h)

    # ── tests ────────────────────────────────────────────────────────────────

    def test_off_without_settings(self):
        with mock.patch.dict(os.environ, {"OIDC_ISSUER": ""}):
            self.assertEqual(self.client.get("/api/auth/oidc/config").json(), {"enabled": False})
            r = self.client.post("/api/auth/login", json={"username": self.mary, "password": "unused-password-123"})
            self.assertEqual(r.status_code, 200)

    def test_half_set_up_stays_off(self):
        with mock.patch.dict(os.environ, {"OIDC_CLIENT_SECRET": ""}):
            self.assertFalse(self.client.get("/api/auth/oidc/config").json()["enabled"])
            r = self.client.post("/api/auth/login", json={"username": self.mary, "password": "unused-password-123"})
            self.assertEqual(r.status_code, 200)

    def test_password_sign_in_refused_except_service_accounts(self):
        cfg = self.client.get("/api/auth/oidc/config").json()
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["account_url"], ISSUER + "/account")
        r = self.client.post("/api/auth/login", json={"username": self.mary, "password": "unused-password-123"})
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/auth/login", json={"username": "guidetest", "password": "guided-test-password-1"})
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/auth/login", json={"username": self.importer, "password": "unused-password-123"})
        self.assertEqual(r.status_code, 200)

    def test_first_sign_in_links_by_username_then_sub_wins(self):
        sub = f"sub-{uuid.uuid4().hex}"
        r = self._sign_in({"sub": sub, "preferred_username": self.mary.upper()})  # case does not matter
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], PUBLIC + "/")
        self.assertEqual(self._me().json()["username"], self.mary)

        # Renamed in Keycloak: still the same library account, because the link is by sub.
        self.client.cookies.clear()
        r = self._sign_in({"sub": sub, "preferred_username": "someone-else"})
        self.assertEqual(r.headers["location"], PUBLIC + "/")
        self.assertEqual(self._me().json()["username"], self.mary)

        # A different Keycloak person with Mary's username cannot take her account.
        self.client.cookies.clear()
        r = self._sign_in({"sub": f"sub-{uuid.uuid4().hex}", "preferred_username": self.mary})
        self.assertEqual(r.headers["location"], PUBLIC + "/?oidc_error=already_linked")
        self.assertEqual(self._me().status_code, 401)

        links = self.client.get("/api/auth/oidc/links", headers=self.h).json()
        self.assertIn(self.mary, [l["library_username"] for l in links])
        self._unlink(self.mary)

    def test_unknown_person_gets_no_account(self):
        r = self._sign_in({"sub": f"sub-{uuid.uuid4().hex}", "preferred_username": f"stranger{self.suffix}"})
        self.assertEqual(r.headers["location"], PUBLIC + "/?oidc_error=no_account")
        self.assertEqual(self._me().status_code, 401)
        conn = self.get_db()
        self.assertIsNone(conn.execute("SELECT 1 FROM users WHERE username=?", (f"stranger{self.suffix}",)).fetchone())
        conn.close()

    def test_service_account_cannot_be_linked(self):
        r = self._sign_in({"sub": f"sub-{uuid.uuid4().hex}", "preferred_username": self.importer})
        self.assertEqual(r.headers["location"], PUBLIC + "/?oidc_error=no_account")

    def test_wrong_nonce_audience_or_expiry_fails(self):
        for bad in ({"nonce": "other"}, {"aud": "another-client"}, {"exp": int(time.time()) - 120},
                    {"iss": "https://evil.example.test"}):
            with self.subTest(bad=bad):
                self.client.cookies.clear()
                self.claims_override = bad
                r = self._sign_in({"sub": f"sub-{uuid.uuid4().hex}", "preferred_username": self.mary})
                self.assertEqual(r.headers["location"], PUBLIC + "/?oidc_error=failed")
                self.assertEqual(self._me().status_code, 401)
        self.claims_override = {}

    def test_state_must_match_this_browser_and_is_single_use(self):
        r = self.client.get("/api/auth/oidc/start", follow_redirects=False)
        state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
        self.client.cookies.clear()  # another browser
        r = self.client.get("/api/auth/oidc/callback", params={"code": "abc", "state": state}, follow_redirects=False)
        self.assertEqual(r.headers["location"], PUBLIC + "/?oidc_error=expired")

        sub = f"sub-{uuid.uuid4().hex}"
        self.client.cookies.clear()
        self.person = {"sub": sub, "preferred_username": self.mary}
        r = self.client.get("/api/auth/oidc/start", follow_redirects=False)
        state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
        conn = self.get_db()
        self.nonce = conn.execute("SELECT nonce FROM oidc_pending WHERE state=?", (state,)).fetchone()["nonce"]
        conn.close()
        cookie = self.client.cookies.get("knitting_oidc_state")
        r = self.client.get("/api/auth/oidc/callback", params={"code": "abc", "state": state}, follow_redirects=False)
        self.assertEqual(r.headers["location"], PUBLIC + "/")
        self.client.cookies.clear()
        self.client.cookies.set("knitting_oidc_state", cookie, path="/api/auth/oidc")
        r = self.client.get("/api/auth/oidc/callback", params={"code": "abc", "state": state}, follow_redirects=False)
        self.assertEqual(r.headers["location"], PUBLIC + "/?oidc_error=expired")
        self._unlink(self.mary)

    def test_cancel_at_keycloak(self):
        r = self.client.get("/api/auth/oidc/callback", params={"error": "access_denied"}, follow_redirects=False)
        self.assertEqual(r.headers["location"], PUBLIC + "/?oidc_error=cancelled")

    def test_links_are_admin_only(self):
        self.assertEqual(self.client.get("/api/auth/oidc/links").status_code, 401)


if __name__ == "__main__":
    unittest.main()
