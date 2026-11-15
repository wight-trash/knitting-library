"""Signing in with Keycloak (OpenID Connect). Fork only, see FORK.md "Signing in with Keycloak", which also holds
the threat model this code is written against.

Switched on by OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, OIDC_PUBLIC_URL and OIDC_USERS. If any is missing or
invalid, Keycloak sign-in stays off (and says why in the log), and upstream's password sign-in works as before.

When it is on:
* /api/auth/oidc/start sends the browser to Keycloak: authorisation code flow, PKCE (S256), state stored on the
  server and tied to the browser by a cookie, nonce;
* /api/auth/oidc/callback checks Keycloak's answer (RFC 9207 `iss`, state, code exchange with the client secret,
  ID token signature with the key and algorithm Keycloak publishes, issuer, audience, azp, expiry, nonce) and
  opens an ordinary upstream session, so the rest of the app cannot tell the difference;
* who may sign in, and as which library account, is decided only by OIDC_USERS: `library_username=keycloak_sub`
  pairs. Usernames and emails from Keycloak are never trusted for this, because the realm lets people create
  Keycloak accounts through Google, Microsoft and other providers and so choose their own usernames;
* password sign-in is refused, except for the non-admin service accounts in OIDC_PASSWORD_LOGIN_USERS
  (default `importer`, the DROPS importer).
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import logging
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode, urlsplit

import httpx
import jwt
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from app.core.foundation import (
    SESSION_LIFETIME_DAYS,
    _auth_fail,
    _auth_ok,
    _set_auth_cookies,
    get_db,
)
from app.fork_migrations import ensure_fork_schema

log = logging.getLogger("knitting.oidc")
auth_log = logging.getLogger("knitting.auth")

STATE_COOKIE = "knitting_oidc_state"
STATE_COOKIE_PATH = "/api/auth/oidc"
CALLBACK_PATH = "/api/auth/oidc/callback"
PENDING_MINUTES = 10
PENDING_MAX_ROWS = 200          # sign-ins in progress kept at most; the oldest go first (bounds what /start can store)
METADATA_TTL = 3600             # discovery document and key set, seconds
MAX_RESPONSE_BYTES = 256 * 1024
MAX_CODE_LEN = 2048
MAX_STATE_LEN = 128
LEEWAY_SECONDS = 30
# Asymmetric only. The algorithm used is the one on the published key, never the one the token claims.
ALLOWED_ALGS = {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"}

_metadata_cache: dict[str, tuple[float, dict]] = {}
_config_problem_logged: str | None = None
_SAFE_LOG = re.compile(r"[^A-Za-z0-9_.@-]")


class OidcConfigError(ValueError):
    pass


def _safe(text: object, limit: int = 64) -> str:
    """For log lines: no newlines or other characters that could fake a log entry."""
    return _SAFE_LOG.sub("?", str(text))[:limit]


# ── Settings ──────────────────────────────────────────────────────────────────

def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_url(name: str, url: str) -> str:
    """https only (plain http just for a loopback address, for local tests), no credentials, query or fragment."""
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname:
        raise OidcConfigError(f"{name} must be an https URL")
    if parts.scheme == "http" and not _is_loopback(parts.hostname):
        raise OidcConfigError(f"{name} must use https")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise OidcConfigError(f"{name} must not contain a user, password, query or fragment")
    return url.rstrip("/")


def _parse_users(raw: str) -> dict[str, str]:
    """OIDC_USERS: `library_username=keycloak_sub` pairs, comma separated. Returns {sub: library username}."""
    users: dict[str, str] = {}
    seen_names: set[str] = set()
    for pair in (p.strip() for p in raw.split(",")):
        if not pair:
            continue
        name, sep, sub = pair.rpartition("=")
        name, sub = name.strip(), sub.strip()
        if not sep or not name or not sub or len(sub) > 255 or any(c.isspace() for c in sub):
            raise OidcConfigError("OIDC_USERS must be library_username=keycloak_user_id pairs, comma separated")
        if sub in users or name.lower() in seen_names:
            raise OidcConfigError("OIDC_USERS names a Keycloak user or a library user twice")
        users[sub] = name
        seen_names.add(name.lower())
    if not users:
        raise OidcConfigError("OIDC_USERS is empty, so nobody could sign in")
    return users


def _load_settings() -> dict | None:
    issuer = os.environ.get("OIDC_ISSUER", "").strip()
    if not issuer:
        return None
    client_id = os.environ.get("OIDC_CLIENT_ID", "").strip()
    client_secret = os.environ.get("OIDC_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise OidcConfigError("OIDC_CLIENT_ID and OIDC_CLIENT_SECRET are needed")
    password_users = {u.strip().lower() for u in os.environ.get("OIDC_PASSWORD_LOGIN_USERS", "importer").split(",") if u.strip()}
    users = _parse_users(os.environ.get("OIDC_USERS", ""))
    if password_users & {n.lower() for n in users.values()}:
        raise OidcConfigError("an account cannot be in both OIDC_USERS and OIDC_PASSWORD_LOGIN_USERS")
    try:
        session_days = int(os.environ.get("OIDC_SESSION_DAYS", "") or SESSION_LIFETIME_DAYS)
    except ValueError:
        raise OidcConfigError("OIDC_SESSION_DAYS must be a whole number of days") from None
    public_url = _check_url("OIDC_PUBLIC_URL", os.environ.get("OIDC_PUBLIC_URL", "").strip())
    if urlsplit(public_url).path not in ("", "/"):
        raise OidcConfigError("OIDC_PUBLIC_URL must be the site address only, without a path")
    return {
        "issuer": _check_url("OIDC_ISSUER", issuer),
        "client_id": client_id,
        "client_secret": client_secret,
        "public_url": public_url,
        "secure_cookies": public_url.startswith("https://"),
        "label": os.environ.get("OIDC_BUTTON_LABEL", "").strip()[:60] or "Sign in",
        "users": users,
        "password_users": password_users,
        "session_days": max(1, min(session_days, SESSION_LIFETIME_DAYS)),
    }


def settings() -> dict | None:
    """The OIDC settings, or None when Keycloak sign-in is off. A broken setting turns it off, logged once."""
    global _config_problem_logged
    try:
        return _load_settings()
    except OidcConfigError as exc:
        if _config_problem_logged != str(exc):
            log.error("Keycloak sign-in is OFF and password sign-in stays on: %s", exc)
            _config_problem_logged = str(exc)
        return None


def refuse_password_login(request: Request, username: str) -> None:
    """Called by upstream's login() before the password is checked. While Keycloak sign-in is on, only the
    non-admin service accounts in OIDC_PASSWORD_LOGIN_USERS may use a password."""
    cfg = settings()
    if not cfg:
        return
    if username.strip().lower() in cfg["password_users"]:
        conn = get_db()
        try:
            row = conn.execute("SELECT is_admin FROM users WHERE lower(username)=lower(?)", (username.strip(),)).fetchone()
        finally:
            conn.close()
        if not row or not row["is_admin"]:
            return  # an unknown name falls through to upstream's normal "incorrect username or password"
        log.error("Password sign-in refused for %s: accounts in OIDC_PASSWORD_LOGIN_USERS must not be admins",
                  _safe(username))
    _auth_fail(request, reason="password_sign_in_off", username=_safe(username))
    raise HTTPException(status_code=403, detail="Password sign-in is switched off. Use the sign-in button.")


def public_config() -> dict:
    cfg = settings()
    if not cfg:
        return {"enabled": False}
    return {"enabled": True, "label": cfg["label"], "account_url": f"{cfg['issuer']}/account"}


# ── Talking to Keycloak ───────────────────────────────────────────────────────

def _get_json(url: str) -> dict:
    """GET over https (TLS checked), no redirects, a time limit and a size limit."""
    _check_url("Keycloak address", url)
    r = httpx.get(url, timeout=10, follow_redirects=False, headers={"Accept": "application/json"})
    r.raise_for_status()
    if len(r.content) > MAX_RESPONSE_BYTES:
        raise ValueError(f"answer from {url} is too large")
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError(f"answer from {url} is not a JSON object")
    return data


def _discovery(issuer: str) -> dict:
    key = f"discovery {issuer}"
    hit = _metadata_cache.get(key)
    if hit and time.monotonic() - hit[0] < METADATA_TTL:
        return hit[1]
    doc = _get_json(f"{issuer}/.well-known/openid-configuration")
    if str(doc.get("issuer", "")).rstrip("/") != issuer:
        raise ValueError(f"discovery names issuer {_safe(doc.get('issuer'), 120)}, expected {issuer}")
    for name in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        _check_url(name, str(doc.get(name, "")))
    if "S256" not in doc.get("code_challenge_methods_supported", ["S256"]):
        raise ValueError("Keycloak does not offer PKCE S256")
    _metadata_cache[key] = (time.monotonic(), doc)
    return doc


def _jwks(uri: str, refresh: bool = False) -> dict:
    # httpx, not PyJWT's PyJWKClient: that uses urllib, whose "Python-urllib" user agent Cloudflare refuses (403).
    key = f"jwks {uri}"
    hit = _metadata_cache.get(key)
    if hit and not refresh and time.monotonic() - hit[0] < METADATA_TTL:
        return hit[1]
    keys = _get_json(uri)
    _metadata_cache[key] = (time.monotonic(), keys)
    return keys


def _signing_key(doc: dict, id_token: str) -> jwt.PyJWK:
    """The published signing key for this token's kid. Encryption keys and symmetric or unknown algorithms are
    skipped. An unknown kid fetches the key set once more, for when Keycloak has rotated its keys (tokens only
    come from Keycloak's token endpoint over TLS, so nobody else can make us refetch)."""
    kid = jwt.get_unverified_header(id_token).get("kid")
    if not kid:
        raise jwt.InvalidTokenError("ID token has no kid")
    for refresh in (False, True):
        usable = [k for k in _jwks(doc["jwks_uri"], refresh=refresh).get("keys", [])
                  if isinstance(k, dict) and k.get("use", "sig") == "sig" and k.get("alg") in ALLOWED_ALGS]
        for key in jwt.PyJWKSet.from_dict({"keys": usable}).keys if usable else []:
            if key.key_id == kid:
                return key
    raise jwt.InvalidTokenError(f"no published signing key with kid {_safe(kid)}")


def _exchange_code(cfg: dict, doc: dict, code: str, verifier: str) -> dict:
    # client_secret_basic, with the id and secret form-encoded first as RFC 6749 section 2.3.1 asks.
    basic = base64.b64encode(f"{quote(cfg['client_id'], safe='')}:{quote(cfg['client_secret'], safe='')}".encode()).decode()
    r = httpx.post(
        doc["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg["public_url"] + CALLBACK_PATH,
            "code_verifier": verifier,
        },
        headers={"Authorization": f"Basic {basic}", "Accept": "application/json"},
        timeout=15,
        follow_redirects=False,
    )
    if r.status_code != 200:
        raise ValueError(f"token endpoint answered {r.status_code}: {_safe(r.text, 200)}")
    if len(r.content) > MAX_RESPONSE_BYTES:
        raise ValueError("token answer is too large")
    tokens = r.json()
    if not isinstance(tokens, dict) or not isinstance(tokens.get("id_token"), str):
        raise ValueError("token answer has no ID token")
    return tokens


def _verify_id_token(cfg: dict, doc: dict, id_token: str, nonce: str) -> dict:
    key = _signing_key(doc, id_token)
    claims = jwt.decode(
        id_token,
        key.key,
        algorithms=[key.algorithm_name],  # the key's algorithm; a token claiming another one is refused
        audience=cfg["client_id"],
        issuer=cfg["issuer"],
        options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        leeway=LEEWAY_SECONDS,
    )
    aud = claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
    if (len(aud) > 1 or "azp" in claims) and claims.get("azp") != cfg["client_id"]:
        raise jwt.InvalidTokenError("azp is not this client")
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise jwt.InvalidTokenError("nonce does not match")
    if not isinstance(claims["sub"], str) or not claims["sub"]:
        raise jwt.InvalidTokenError("sub is empty")
    return claims


# ── Flow ──────────────────────────────────────────────────────────────────────

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _no_store(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    # Referrer-Policy comes from upstream's security headers (strict-origin-when-cross-origin), so the code and
    # state in these URLs never go to another site.
    return resp


def _force_secure_cookies(resp, cfg: dict):
    """The site is https (OIDC_PUBLIC_URL) even when the app cannot tell, because TLS ends at the proxy and
    TRUSTED_PROXIES is not set. Upstream then leaves Secure off its session cookies; add it here."""
    if not cfg["secure_cookies"]:
        return resp
    resp.raw_headers[:] = [  # in place: Starlette sends this same list
        (k, v + b"; Secure") if k.lower() == b"set-cookie" and b"secure" not in v.lower() else (k, v)
        for k, v in resp.raw_headers
    ]
    return resp


def _back_to_app(cfg: dict, error: str | None = None) -> RedirectResponse:
    # Only fixed codes ever go into the address, and only to our own site.
    resp = RedirectResponse(cfg["public_url"] + "/" + (f"?oidc_error={error}" if error else ""), status_code=303)
    resp.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH, secure=cfg["secure_cookies"], httponly=True, samesite="lax")
    return _no_store(resp)


def start(request: Request):
    cfg = settings()
    if not cfg:
        raise HTTPException(status_code=404, detail="Keycloak sign-in is not switched on")
    try:
        doc = _discovery(cfg["issuer"])
    except Exception as exc:  # Keycloak down, or answering wrongly
        log.warning("Keycloak sign-in unavailable (%s): %s", type(exc).__name__, _safe(exc, 300))
        return _back_to_app(cfg, "unavailable")
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    now = datetime.utcnow()
    ensure_fork_schema()
    conn = get_db()
    try:
        conn.execute("DELETE FROM oidc_pending WHERE created_at < ?", ((now - timedelta(minutes=PENDING_MINUTES)).isoformat(),))
        conn.execute("DELETE FROM oidc_pending WHERE state NOT IN "
                     "(SELECT state FROM oidc_pending ORDER BY created_at DESC LIMIT ?)", (PENDING_MAX_ROWS - 1,))
        conn.execute("INSERT INTO oidc_pending (state, nonce, code_verifier, created_at) VALUES (?,?,?,?)",
                     (state, nonce, verifier, now.isoformat()))
        conn.commit()
    finally:
        conn.close()
    query = urlencode({
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["public_url"] + CALLBACK_PATH,
        "scope": "openid",
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
    })
    resp = RedirectResponse(f"{doc['authorization_endpoint']}?{query}", status_code=303)
    # Ties the sign-in to this browser, so nobody can finish their own sign-in in someone else's browser.
    resp.set_cookie(STATE_COOKIE, state, max_age=PENDING_MINUTES * 60, httponly=True,
                    secure=cfg["secure_cookies"], samesite="lax", path=STATE_COOKIE_PATH)
    return _no_store(resp)


def _user_for(conn, cfg: dict, sub: str) -> dict | None:
    """The library account OIDC_USERS gives this Keycloak user, or None."""
    name = cfg["users"].get(sub)
    if not name:
        return None
    rows = conn.execute("SELECT * FROM users WHERE lower(username)=lower(?)", (name,)).fetchall()
    if len(rows) != 1:
        log.error("OIDC_USERS names library account %s, which %s", _safe(name),
                  "does not exist" if not rows else "matches more than one account (case)")
        return None
    return dict(rows[0])


def _record_sign_in(conn, cfg: dict, user: dict, sub: str, claims: dict, now: datetime) -> None:
    row = conn.execute("SELECT subject FROM oidc_identities WHERE user_id=?", (user["id"],)).fetchone()
    if row is None:
        auth_log.info("OIDC_LINK user=%s sub=%s", _safe(user["username"]), _safe(sub, 255))
    elif row["subject"] != sub:
        auth_log.warning("OIDC_RELINK user=%s old_sub=%s new_sub=%s", _safe(user["username"]),
                         _safe(row["subject"], 255), _safe(sub, 255))
    # One row per library account; the subject column follows OIDC_USERS.
    conn.execute("DELETE FROM oidc_identities WHERE (issuer=? AND subject=?) AND user_id<>?", (cfg["issuer"], sub, user["id"]))
    conn.execute(
        "INSERT INTO oidc_identities (user_id, issuer, subject, username, linked_at, last_login) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET issuer=excluded.issuer, subject=excluded.subject, "
        "username=excluded.username, last_login=excluded.last_login",
        (user["id"], cfg["issuer"], sub, _safe(claims.get("preferred_username", ""), 100), now.isoformat(), now.isoformat()),
    )


def callback(request: Request, code: str = "", state: str = "", error: str = "", iss: str = ""):
    cfg = settings()
    if not cfg:
        raise HTTPException(status_code=404, detail="Keycloak sign-in is not switched on")
    if error:  # the person pressed cancel, or Keycloak refused
        _auth_fail(request, reason=f"oidc_{_safe(error, 40)}")
        return _back_to_app(cfg, "cancelled")
    cookie_state = request.cookies.get(STATE_COOKIE, "")
    if (not code or not state or not cookie_state or len(code) > MAX_CODE_LEN or len(state) > MAX_STATE_LEN
            or not secrets.compare_digest(state.encode(), cookie_state.encode())):
        _auth_fail(request, reason="oidc_bad_state")
        return _back_to_app(cfg, "expired")

    ensure_fork_schema()
    conn = get_db()
    try:
        pending = conn.execute("SELECT * FROM oidc_pending WHERE state=?", (state,)).fetchone()
        conn.execute("DELETE FROM oidc_pending WHERE state=?", (state,))  # single use, whatever happens next
        conn.commit()
        if not pending or pending["created_at"] < (datetime.utcnow() - timedelta(minutes=PENDING_MINUTES)).isoformat():
            _auth_fail(request, reason="oidc_expired")
            return _back_to_app(cfg, "expired")
        try:
            doc = _discovery(cfg["issuer"])
            # RFC 9207: the answer must come from our issuer (defends against mix-up attacks).
            if iss or doc.get("authorization_response_iss_parameter_supported"):
                if iss.rstrip("/") != cfg["issuer"]:
                    raise ValueError("iss in the answer is missing or not our issuer")
            tokens = _exchange_code(cfg, doc, code, pending["code_verifier"])
            claims = _verify_id_token(cfg, doc, tokens["id_token"], pending["nonce"])
        except Exception as exc:
            log.warning("Keycloak sign-in failed (%s): %s", type(exc).__name__, _safe(exc, 300))
            _auth_fail(request, reason="oidc_failed")
            return _back_to_app(cfg, "failed")

        sub = claims["sub"]
        user = _user_for(conn, cfg, sub)
        if not user:
            # Logged with the Keycloak user id, so an admin adding someone to OIDC_USERS can copy it from here.
            auth_log.warning("OIDC_NOT_ALLOWED sub=%s username=%s", _safe(sub, 255), _safe(claims.get("preferred_username", "")))
            _auth_fail(request, reason="oidc_not_allowed", username=_safe(claims.get("preferred_username", "")))
            return _back_to_app(cfg, "no_account")

        token = secrets.token_hex(32)
        now = datetime.utcnow()
        try:
            _record_sign_in(conn, cfg, user, sub, claims, now)
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_date, expires_at, is_challenge) VALUES (?,?,?,?,0)",
                (token, user["id"], now.isoformat(), (now + timedelta(days=cfg["session_days"])).isoformat()),
            )
            conn.commit()
        except sqlite3.Error as exc:
            conn.rollback()
            log.error("Keycloak sign-in could not be saved: %s", _safe(exc, 200))
            return _back_to_app(cfg, "failed")
    finally:
        conn.close()

    _auth_ok(request, user["username"])
    resp = _back_to_app(cfg)
    _set_auth_cookies(resp, token, request)
    return _force_secure_cookies(resp, cfg)


# ── Keeping sessions in step with OIDC_USERS ──────────────────────────────────

def sync_on_startup() -> None:
    """At start-up: anyone who signed in with Keycloak but is no longer in OIDC_USERS (or now has another Keycloak
    user) loses their library sessions. So taking someone out of OIDC_USERS and restarting really locks them out."""
    cfg = settings()
    if not cfg:
        return
    ensure_fork_schema()
    conn = get_db()
    try:
        for name in sorted(cfg["password_users"]):
            row = conn.execute("SELECT username FROM users WHERE lower(username)=? AND is_admin=1", (name,)).fetchone()
            if row:
                log.error("Service account %s is an admin, so its password sign-in is refused. Service accounts must be "
                          "ordinary members (FORK.md, \"Signing in with Keycloak\").", _safe(row["username"]))
        allowed = {name.lower(): sub for sub, name in cfg["users"].items()}
        rows = conn.execute("SELECT o.user_id, o.subject, o.issuer, u.username FROM oidc_identities o "
                            "LEFT JOIN users u ON u.id=o.user_id").fetchall()
        for r in rows:
            if r["username"] is None:  # library account deleted
                conn.execute("DELETE FROM oidc_identities WHERE user_id=?", (r["user_id"],))
                continue
            if allowed.get(r["username"].lower()) != r["subject"] or r["issuer"] != cfg["issuer"]:
                gone = conn.execute("DELETE FROM sessions WHERE user_id=?", (r["user_id"],)).rowcount
                conn.execute("DELETE FROM oidc_identities WHERE user_id=?", (r["user_id"],))
                auth_log.warning("OIDC_REVOKED user=%s sessions=%d (no longer in OIDC_USERS)", _safe(r["username"]), gone)
        conn.commit()
    finally:
        conn.close()


def linked_accounts() -> list[dict]:
    """For the admin: OIDC_USERS, and when each account last signed in with Keycloak."""
    cfg = settings()
    if not cfg:
        return []
    ensure_fork_schema()
    conn = get_db()
    try:
        out = []
        for sub, name in sorted(cfg["users"].items(), key=lambda kv: kv[1].lower()):
            user = conn.execute("SELECT id, username FROM users WHERE lower(username)=lower(?)", (name,)).fetchone()
            seen = conn.execute("SELECT last_login FROM oidc_identities WHERE user_id=? AND subject=?",
                                (user["id"], sub)).fetchone() if user else None
            out.append({"library_username": user["username"] if user else name, "exists": bool(user),
                        "keycloak_user_id": sub, "last_login": seen["last_login"] if seen else None})
        return out
    finally:
        conn.close()
