"""Signing in with Keycloak (FORK.md "Signing in with Keycloak"), end to end through the API.

Keycloak is replaced by a fake at the network edge only: the discovery document, the published key set and the
token endpoint are patched. ID tokens are real signed JWTs, and the key lookup, algorithm, signature, issuer,
audience, azp, expiry and nonce checks all run for real. Each test is named after the attack or mistake it covers.

Needs KNITTING_DATA_DIR, KNITTING_LOG_DIR and KNITTING_STATIC_DIR set to temporary folders, as the other API tests do.
"""
import base64
import json
import os
import time
import unittest
import uuid
from datetime import datetime, timedelta
from unittest import mock
from urllib.parse import parse_qs, unquote, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

ISSUER = "https://auth.example.test/realms/test"
PUBLIC = "https://knit.example.test"
SECRET = "s3cret:with/odd+chars"
DOC = {
    "issuer": ISSUER,
    "authorization_endpoint": f"{ISSUER}/protocol/openid-connect/auth",
    "token_endpoint": f"{ISSUER}/protocol/openid-connect/token",
    "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs",
    "code_challenge_methods_supported": ["plain", "S256"],
    "authorization_response_iss_parameter_supported": True,
}
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ENC_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(key, kid, use="sig", alg="RS256"):
    d = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    d.update(kid=kid, use=use, alg=alg)
    return d


JWKS = {"keys": [_jwk(ENC_KEY, "enc-1", "enc", "RSA-OAEP"), _jwk(KEY, "k1")]}


class OidcFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main
        from app.core.foundation import get_db

        cls.get_db = staticmethod(get_db)
        cls.app = main.app
        cls.client = TestClient(main.app, base_url=PUBLIC)
        cls.client.__enter__()
        status = cls.client.get("/api/setup/status").json()
        if status.get("setup_required"):
            tok = cls.client.post("/api/setup/admin", json={"username": "guidetest", "password": "guided-test-password-1"}).json()["token"]
        else:  # another test created the admin already
            tok = cls.client.post("/api/auth/login", json={"username": "guidetest", "password": "guided-test-password-1"}).json().get("token")
        cls.h = {"X-Session-Token": tok}
        cls.client.cookies.clear()
        sfx = uuid.uuid4().hex[:6]
        cls.mary, cls.boss, cls.importer, cls.adminsvc = f"Mary{sfx}", f"boss{sfx}", f"importer{sfx}", f"adminsvc{sfx}"
        for name, admin in ((cls.mary, False), (cls.boss, True), (cls.importer, False), (cls.adminsvc, True)):
            r = cls.client.post("/api/admin/users", headers=cls.h,
                                json={"username": name, "password": "unused-password-123", "is_admin": admin})
            assert r.status_code == 200, r.text
        cls.mary_sub, cls.boss_sub = str(uuid.uuid4()), str(uuid.uuid4())

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def env(self, **over):
        base = {
            "OIDC_ISSUER": ISSUER, "OIDC_CLIENT_ID": "knitting", "OIDC_CLIENT_SECRET": SECRET,
            "OIDC_PUBLIC_URL": PUBLIC, "OIDC_PASSWORD_LOGIN_USERS": f"{self.importer},{self.adminsvc}",
            "OIDC_USERS": f"{self.mary.lower()}={self.mary_sub}, {self.boss}={self.boss_sub}",
            "OIDC_SESSION_DAYS": "",
        }
        base.update(over)
        return mock.patch.dict(os.environ, base)

    def setUp(self):
        from app.oidc import service
        self.service = service
        service._metadata_cache.clear()
        self.client.cookies.clear()
        e = self.env()
        e.start()
        self.addCleanup(e.stop)
        self.token_claims = {}       # extra/overriding claims for the next ID token
        self.token_header = {"kid": "k1"}
        self.token_key, self.token_alg = KEY, "RS256"
        self.exchanged = []
        for p in (mock.patch.object(service, "_discovery", side_effect=lambda issuer: DOC),
                  mock.patch.object(service, "_jwks", side_effect=lambda uri, refresh=False: JWKS),
                  mock.patch.object(service.httpx, "post", side_effect=self._token_endpoint)):
            p.start()
            self.addCleanup(p.stop)

    # The fake token endpoint: checks what a real one would, then answers with an ID token for self.person.
    def _token_endpoint(self, url, data, headers, timeout, follow_redirects):
        self.assertEqual(url, DOC["token_endpoint"])
        self.assertFalse(follow_redirects)
        user, _, pw = base64.b64decode(headers["Authorization"][6:]).decode().partition(":")
        self.assertEqual((unquote(user), unquote(pw)), ("knitting", SECRET))
        self.exchanged.append(data)
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "knitting", "iat": now, "exp": now + 300, "nonce": self.nonce, **self.person,
                  **self.token_claims}
        tok = jwt.encode(claims, self.token_key, algorithm=self.token_alg, headers=self.token_header)
        body = json.dumps({"id_token": tok, "access_token": "x"}).encode()
        return mock.Mock(status_code=200, content=body, text=body.decode(), json=lambda: json.loads(body))

    def _start(self):
        r = self.client.get("/api/auth/oidc/start", follow_redirects=False)
        self.assertEqual(r.status_code, 303, r.text)
        q = parse_qs(urlparse(r.headers["location"]).query)
        state = q["state"][0]
        conn = self.get_db()
        row = conn.execute("SELECT nonce, code_verifier FROM oidc_pending WHERE state=?", (state,)).fetchone()
        conn.close()
        self.nonce, self.verifier = row["nonce"], row["code_verifier"]
        return r, q, state

    def _sign_in(self, person, iss=ISSUER, **cb):
        self.person = person
        r, q, state = self._start()
        params = {"code": "abc", "state": state, **({"iss": iss} if iss is not None else {}), **cb}
        return self.client.get("/api/auth/oidc/callback", params=params, follow_redirects=False)

    def _me(self):
        return self.client.get("/api/auth/me")

    def assertRefused(self, r, code):
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], f"{PUBLIC}/?oidc_error={code}")
        self.assertEqual(self._me().status_code, 401)

    def assertSignedInAs(self, r, name):
        self.assertEqual(r.headers["location"], PUBLIC + "/", r.headers["location"])
        self.assertEqual(self._me().json()["username"], name)

    # ── switching on and off ────────────────────────────────────────────────

    def test_off_without_issuer_keeps_password_sign_in(self):
        with self.env(OIDC_ISSUER=""):
            self.assertEqual(self.client.get("/api/auth/oidc/config").json(), {"enabled": False})
            self.assertEqual(self.client.get("/api/auth/oidc/start", follow_redirects=False).status_code, 404)
            r = self.client.post("/api/auth/login", json={"username": self.mary, "password": "unused-password-123"})
            self.assertEqual(r.status_code, 200)

    def test_broken_settings_turn_it_off_instead_of_locking_everyone_out(self):
        cases = {
            "no secret": {"OIDC_CLIENT_SECRET": ""},
            "no users": {"OIDC_USERS": ""},
            "malformed users": {"OIDC_USERS": "mary"},
            "same sub twice": {"OIDC_USERS": f"a=x,b=x"},
            "same user twice": {"OIDC_USERS": f"a=x,A=y"},
            "http issuer": {"OIDC_ISSUER": "http://auth.example.test/realms/test"},
            "http public url": {"OIDC_PUBLIC_URL": "http://knit.example.test"},
            "public url with path": {"OIDC_PUBLIC_URL": PUBLIC + "/library"},
            "issuer with query": {"OIDC_ISSUER": ISSUER + "?x=1"},
            "service account also in users": {"OIDC_PASSWORD_LOGIN_USERS": self.mary},
            "bad session days": {"OIDC_SESSION_DAYS": "a week"},
        }
        for name, over in cases.items():
            with self.subTest(name), self.env(**over):
                self.assertFalse(self.client.get("/api/auth/oidc/config").json()["enabled"])
                r = self.client.post("/api/auth/login", json={"username": self.mary, "password": "unused-password-123"})
                self.assertEqual(r.status_code, 200)
                self.client.cookies.clear()

    def test_loopback_http_is_allowed_for_local_testing_only(self):
        with self.env(OIDC_ISSUER="http://127.0.0.1:9/realms/t", OIDC_PUBLIC_URL="http://localhost:8080"):
            self.assertTrue(self.client.get("/api/auth/oidc/config").json()["enabled"])

    # ── password sign-in ────────────────────────────────────────────────────

    def test_password_sign_in_is_refused_except_for_non_admin_service_accounts(self):
        for name in (self.mary, self.boss, "guidetest", "nobody-at-all"):
            with self.subTest(name):
                r = self.client.post("/api/auth/login", json={"username": name, "password": "unused-password-123"})
                self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/auth/login", json={"username": self.importer, "password": "unused-password-123"})
        self.assertEqual(r.status_code, 200)
        # An admin put in OIDC_PASSWORD_LOGIN_USERS by mistake still cannot use a password.
        r = self.client.post("/api/auth/login", json={"username": self.adminsvc, "password": "unused-password-123"})
        self.assertEqual(r.status_code, 403)

    # ── who gets in ─────────────────────────────────────────────────────────

    def test_listed_keycloak_user_signs_in_to_their_account(self):
        r = self._sign_in({"sub": self.mary_sub, "preferred_username": "mary"})
        self.assertSignedInAs(r, self.mary)
        self.assertEqual(self.exchanged[-1]["code_verifier"], self.verifier)

    def test_username_from_keycloak_is_never_trusted(self):
        # The takeover: someone makes a Keycloak account (say through Google) with the admin's username.
        r = self._sign_in({"sub": str(uuid.uuid4()), "preferred_username": self.boss, "email": "x@example.test"})
        self.assertRefused(r, "no_account")
        # And a listed person renamed in Keycloak still lands in their own account.
        self.client.cookies.clear()
        r = self._sign_in({"sub": self.boss_sub, "preferred_username": "renamed"})
        self.assertSignedInAs(r, self.boss)

    def test_listed_but_missing_library_account_is_refused(self):
        sub = str(uuid.uuid4())
        with self.env(OIDC_USERS=f"ghost{uuid.uuid4().hex[:6]}={sub}"):
            self.assertRefused(self._sign_in({"sub": sub}), "no_account")

    # ── the ID token ────────────────────────────────────────────────────────

    def test_tampered_or_wrong_tokens_are_refused(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = int(time.time())
        cases = {
            "wrong nonce (replayed token)": dict(claims={"nonce": "other"}),
            "other client's token": dict(claims={"aud": "another-client"}),
            "expired": dict(claims={"exp": now - 120, "iat": now - 400}),
            "other issuer": dict(claims={"iss": "https://evil.example.test"}),
            "azp names another client": dict(claims={"aud": ["knitting", "other"], "azp": "other"}),
            "azp missing with two audiences": dict(claims={"aud": ["knitting", "other"]}),
            "signed by another key": dict(key=other),
            "alg confusion: HS256 with the client secret": dict(key=SECRET, alg="HS256"),
            "alg differs from the published key's": dict(alg="RS512"),
            "unknown kid": dict(header={"kid": "nope"}),
            "no kid": dict(header={}),
            "signed with the encryption key": dict(key=ENC_KEY, header={"kid": "enc-1"}),
        }
        for name, case in cases.items():
            with self.subTest(name):
                self.client.cookies.clear()
                self.token_claims = case.get("claims", {})
                self.token_key = case.get("key", KEY)
                self.token_alg = case.get("alg", "RS256")
                self.token_header = case.get("header", {"kid": "k1"})
                self.assertRefused(self._sign_in({"sub": self.mary_sub}), "failed")

    def test_answer_from_another_issuer_is_refused_rfc9207(self):
        self.assertRefused(self._sign_in({"sub": self.mary_sub}, iss="https://evil.example.test/realms/x"), "failed")
        self.client.cookies.clear()
        self.assertRefused(self._sign_in({"sub": self.mary_sub}, iss=None), "failed")  # Keycloak always sends it

    # ── state and the browser ───────────────────────────────────────────────

    def test_state_from_another_browser_is_refused(self):
        self.person = {"sub": self.mary_sub}
        _, _, attacker_state = self._start()  # the attacker starts a sign-in in their own browser...
        self.client.cookies.clear()
        r = self.client.get("/api/auth/oidc/callback", params={"code": "abc", "state": attacker_state, "iss": ISSUER},
                            follow_redirects=False)
        self.assertRefused(r, "expired")  # ...and a victim's browser with no sign-in of its own refuses it
        self.client.cookies.clear()
        self._start()  # a victim's browser that has started its own sign-in (its own state cookie) refuses it too
        r = self.client.get("/api/auth/oidc/callback", params={"code": "abc", "state": attacker_state, "iss": ISSUER},
                            follow_redirects=False)
        self.assertRefused(r, "expired")
        self.assertEqual(self.exchanged, [])  # never reached Keycloak

    def test_state_is_single_use(self):
        self.person = {"sub": self.mary_sub}
        _, _, state = self._start()
        cookie = self.client.cookies.get("knitting_oidc_state")
        params = {"code": "abc", "state": state, "iss": ISSUER}
        self.assertSignedInAs(self.client.get("/api/auth/oidc/callback", params=params, follow_redirects=False), self.mary)
        self.client.cookies.clear()
        self.client.cookies.set("knitting_oidc_state", cookie, domain="knit.example.test", path="/api/auth/oidc")
        self.assertRefused(self.client.get("/api/auth/oidc/callback", params=params, follow_redirects=False), "expired")

    def test_expired_sign_in_is_refused(self):
        self.person = {"sub": self.mary_sub}
        _, _, state = self._start()
        conn = self.get_db()
        conn.execute("UPDATE oidc_pending SET created_at=? WHERE state=?",
                     ((datetime.utcnow() - timedelta(minutes=11)).isoformat(), state))
        conn.commit()
        conn.close()
        r = self.client.get("/api/auth/oidc/callback", params={"code": "abc", "state": state, "iss": ISSUER},
                            follow_redirects=False)
        self.assertRefused(r, "expired")

    def test_oversized_parameters_are_refused_before_any_work(self):
        self.person = {"sub": self.mary_sub}
        _, _, state = self._start()
        r = self.client.get("/api/auth/oidc/callback", params={"code": "c" * 5000, "state": state, "iss": ISSUER},
                            follow_redirects=False)
        self.assertRefused(r, "expired")
        self.assertEqual(self.exchanged, [])

    def test_cancel_at_keycloak_and_log_injection(self):
        r = self.client.get("/api/auth/oidc/callback", params={"error": "access_denied\nAUTH_OK user=boss"},
                            follow_redirects=False)
        self.assertRefused(r, "cancelled")
        self.assertNotIn("\n", self.service._safe("a\nb\r\x00c"))

    def test_pending_sign_ins_are_bounded(self):
        for _ in range(self.service.PENDING_MAX_ROWS + 20):
            self.client.get("/api/auth/oidc/start", follow_redirects=False)
        conn = self.get_db()
        n = conn.execute("SELECT COUNT(*) FROM oidc_pending").fetchone()[0]
        conn.close()
        self.assertLessEqual(n, self.service.PENDING_MAX_ROWS)

    # ── cookies and headers ─────────────────────────────────────────────────

    def test_cookies_are_secure_even_when_the_proxy_is_not_trusted(self):
        plain = TestClient(self.app, base_url="http://knit.example.test")  # TLS ended at the proxy
        self.person = {"sub": self.mary_sub}
        r = plain.get("/api/auth/oidc/start", follow_redirects=False)
        state_cookie = r.headers["set-cookie"]
        for part in ("HttpOnly", "Secure", "Path=/api/auth/oidc", "SameSite=lax"):
            self.assertIn(part.lower(), state_cookie.lower())
        self.assertEqual(r.headers["cache-control"], "no-store")
        self.assertIn(r.headers["referrer-policy"], ("no-referrer", "strict-origin-when-cross-origin", "same-origin"))
        state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
        conn = self.get_db()
        self.nonce = conn.execute("SELECT nonce FROM oidc_pending WHERE state=?", (state,)).fetchone()["nonce"]
        conn.close()
        r = plain.get("/api/auth/oidc/callback", params={"code": "abc", "state": state, "iss": ISSUER},
                      headers={"Cookie": f"knitting_oidc_state={state}"}, follow_redirects=False)
        self.assertEqual(r.headers["location"], PUBLIC + "/")
        cookies = r.headers.get_list("set-cookie")
        self.assertGreaterEqual(len(cookies), 3)  # session, CSRF, and the state cookie removed
        for c in cookies:
            self.assertIn("secure", c.lower(), c)

    def test_session_length_follows_setting(self):
        with self.env(OIDC_SESSION_DAYS="2"):
            self.assertSignedInAs(self._sign_in({"sub": self.mary_sub}), self.mary)
        conn = self.get_db()
        exp = conn.execute("SELECT MAX(expires_at) FROM sessions s JOIN users u ON u.id=s.user_id WHERE u.username=?",
                           (self.mary,)).fetchone()[0]
        conn.close()
        self.assertLess(datetime.fromisoformat(exp), datetime.utcnow() + timedelta(days=2, minutes=1))

    # ── taking someone off the list ─────────────────────────────────────────

    def test_removing_someone_from_oidc_users_ends_their_sessions_at_restart(self):
        self.assertSignedInAs(self._sign_in({"sub": self.boss_sub}), self.boss)
        with self.env(OIDC_USERS=f"{self.mary}={self.mary_sub}"):
            self.service.sync_on_startup()
        self.assertEqual(self._me().status_code, 401)
        # And giving the account to another Keycloak user does the same.
        self.client.cookies.clear()
        self.assertSignedInAs(self._sign_in({"sub": self.mary_sub}), self.mary)
        with self.env(OIDC_USERS=f"{self.mary}={uuid.uuid4()},{self.boss}={self.boss_sub}"):
            self.service.sync_on_startup()
        self.assertEqual(self._me().status_code, 401)

    def test_admin_service_account_is_reported_at_startup(self):
        with self.assertLogs("knitting.oidc", level="ERROR") as logs:
            self.service.sync_on_startup()
        self.assertTrue(any(self.adminsvc in line and "is an admin" in line for line in logs.output))
        self.assertFalse(any(self.importer in line for line in logs.output))

    def test_admin_list(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/auth/oidc/links").status_code, 401)
        links = self.client.get("/api/auth/oidc/links", headers=self.h).json()
        self.assertEqual({l["keycloak_user_id"] for l in links}, {self.mary_sub, self.boss_sub})


class NetworkEdgeTests(unittest.TestCase):
    """What is fetched from Keycloak, and how."""

    def setUp(self):
        from app.oidc import service
        self.service = service
        service._metadata_cache.clear()
        self.addCleanup(service._metadata_cache.clear)

    @staticmethod
    def _resp(obj):
        body = json.dumps(obj).encode()
        return mock.Mock(raise_for_status=lambda: None, content=body, json=lambda: json.loads(body))

    def test_discovery_must_match_the_issuer_and_use_https(self):
        for bad in ({**DOC, "issuer": "https://evil.example.test"},
                    {**DOC, "token_endpoint": "http://auth.example.test/token"},
                    {**DOC, "code_challenge_methods_supported": ["plain"]}):
            with self.subTest(bad=bad), mock.patch.object(self.service.httpx, "get", return_value=self._resp(bad)):
                self.service._metadata_cache.clear()
                with self.assertRaises(ValueError):
                    self.service._discovery(ISSUER)

    def test_fetches_use_httpx_without_redirects_and_with_a_size_limit(self):
        calls = []

        def fake_get(url, timeout, follow_redirects, headers):
            calls.append((url, follow_redirects))
            return self._resp(DOC)

        with mock.patch.object(self.service.httpx, "get", side_effect=fake_get):
            self.service._discovery(ISSUER)
        self.assertEqual(calls, [(ISSUER + "/.well-known/openid-configuration", False)])
        big = mock.Mock(raise_for_status=lambda: None, content=b"x" * (self.service.MAX_RESPONSE_BYTES + 1))
        with mock.patch.object(self.service.httpx, "get", return_value=big):
            with self.assertRaises(ValueError):
                self.service._jwks(DOC["jwks_uri"], refresh=True)

    def test_only_asymmetric_signing_keys_are_used(self):
        mislabelled = _jwk(ENC_KEY, "enc-but-rs256", use="enc", alg="RS256")
        symmetric = {"kty": "oct", "k": base64.urlsafe_b64encode(b"k" * 32).rstrip(b"=").decode(), "kid": "hs", "alg": "HS256", "use": "sig"}
        jwks = {"keys": [mislabelled, symmetric, _jwk(KEY, "k1")]}
        with mock.patch.object(self.service, "_jwks", return_value=jwks):
            for kid in ("enc-but-rs256", "hs"):
                with self.subTest(kid):
                    token = jwt.encode({"sub": "x"}, KEY, algorithm="RS256", headers={"kid": kid})
                    with self.assertRaises(jwt.InvalidTokenError):
                        self.service._signing_key(DOC, token)
            token = jwt.encode({"sub": "x"}, KEY, algorithm="RS256", headers={"kid": "k1"})
            self.assertEqual(self.service._signing_key(DOC, token).key_id, "k1")

    def test_new_kid_fetches_the_key_set_again_once(self):
        answers = [{"keys": [_jwk(KEY, "old")]}, {"keys": [_jwk(KEY, "new")]}]
        with mock.patch.object(self.service.httpx, "get", side_effect=lambda *a, **k: self._resp(answers.pop(0))):
            token = jwt.encode({"sub": "x"}, KEY, algorithm="RS256", headers={"kid": "new"})
            key = self.service._signing_key(DOC, token)
        self.assertEqual(key.key_id, "new")
        self.assertEqual(answers, [])


if __name__ == "__main__":
    unittest.main()
