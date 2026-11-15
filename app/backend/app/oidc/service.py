"""Signing in with Keycloak (OpenID Connect). Fork only, see FORK.md "Signing in with Keycloak".

Switched on by OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET and OIDC_PUBLIC_URL. Without them nothing here
does anything and upstream's password sign-in works as before.

When it is on:
* /api/auth/oidc/start sends the browser to Keycloak (authorisation code flow with PKCE, state and nonce);
* /api/auth/oidc/callback checks Keycloak's answer and opens an ordinary upstream session (the same `sessions`
  row and cookies as a password sign-in), so the rest of the app cannot tell the difference;
* a person is found by their Keycloak id (issuer + "sub") in `oidc_identities`. The first time, an existing
  library account with the same username as their Keycloak username is linked to it. That keeps their
  notes, row counters, reading places and project history. Nobody gets a new account this way: an admin
  creates the library account first (any password, it is never used);
* password sign-in is refused, except for the accounts in OIDC_PASSWORD_LOGIN_USERS (default `importer`,
  the DROPS importer's service account).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from app.core.foundation import (
    SESSION_LIFETIME_DAYS,
    _ALLOWED_ORIGINS,
    _auth_fail,
    _auth_ok,
    _is_secure_request,
    _set_auth_cookies,
    get_db,
)
from app.fork_migrations import ensure_fork_schema

log = logging.getLogger("knitting.oidc")

STATE_COOKIE = "knitting_oidc_state"
PENDING_MINUTES = 10
DISCOVERY_TTL = 3600
CALLBACK_PATH = "/api/auth/oidc/callback"

_discovery_cache: dict[str, tuple[float, dict]] = {}
_warned_incomplete = False


# ── Settings ──────────────────────────────────────────────────────────────────

def settings() -> dict | None:
    """The OIDC settings, or None when signing in with Keycloak is off (or only half set up)."""
    global _warned_incomplete
    issuer = os.environ.get("OIDC_ISSUER", "").strip().rstrip("/")
    if not issuer:
        return None
    public_url = (os.environ.get("OIDC_PUBLIC_URL", "").strip() or (_ALLOWED_ORIGINS[0] if _ALLOWED_ORIGINS else "")).rstrip("/")
    cfg = {
        "issuer": issuer,
        "client_id": os.environ.get("OIDC_CLIENT_ID", "").strip(),
        "client_secret": os.environ.get("OIDC_CLIENT_SECRET", "").strip(),
        "public_url": public_url,
        "username_claim": os.environ.get("OIDC_USERNAME_CLAIM", "preferred_username").strip() or "preferred_username",
        "label": os.environ.get("OIDC_BUTTON_LABEL", "").strip() or "Sign in",
        "password_users": {
            u.strip().lower()
            for u in os.environ.get("OIDC_PASSWORD_LOGIN_USERS", "importer").split(",")
            if u.strip()
        },
    }
    if not (cfg["client_id"] and cfg["client_secret"] and cfg["public_url"]):
        # Half set up: keep password sign-in rather than lock everybody out.
        if not _warned_incomplete:
            log.warning("OIDC_ISSUER is set but OIDC_CLIENT_ID, OIDC_CLIENT_SECRET or OIDC_PUBLIC_URL is missing; "
                        "Keycloak sign-in stays off and password sign-in stays on")
            _warned_incomplete = True
        return None
    return cfg


def refuse_password_login(request: Request, username: str) -> None:
    """Called by upstream's login(): password sign-in is off while Keycloak sign-in is on, except for service accounts."""
    cfg = settings()
    if not cfg or username.strip().lower() in cfg["password_users"]:
        return
    _auth_fail(request, reason="password_sign_in_off", username=username)
    raise HTTPException(status_code=403, detail="Password sign-in is switched off. Use the sign-in button.")


def public_config() -> dict:
    cfg = settings()
    if not cfg:
        return {"enabled": False}
    return {"enabled": True, "label": cfg["label"], "account_url": f"{cfg['issuer']}/account"}


# ── Talking to Keycloak (kept small so tests can replace them) ────────────────

def _discovery(issuer: str) -> dict:
    hit = _discovery_cache.get(issuer)
    if hit and time.monotonic() - hit[0] < DISCOVERY_TTL:
        return hit[1]
    r = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=10)
    r.raise_for_status()
    doc = r.json()
    if doc.get("issuer", "").rstrip("/") != issuer:
        raise RuntimeError(f"discovery issuer {doc.get('issuer')!r} does not match {issuer!r}")
    _discovery_cache[issuer] = (time.monotonic(), doc)
    return doc


def _exchange_code(cfg: dict, doc: dict, code: str, verifier: str) -> dict:
    r = httpx.post(
        doc["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg["public_url"] + CALLBACK_PATH,
            "code_verifier": verifier,
        },
        auth=(cfg["client_id"], cfg["client_secret"]),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _signing_key(doc: dict, id_token: str):
    return jwt.PyJWKClient(doc["jwks_uri"], cache_keys=True).get_signing_key_from_jwt(id_token).key


def _verify_id_token(cfg: dict, doc: dict, id_token: str, nonce: str) -> dict:
    claims = jwt.decode(
        id_token,
        _signing_key(doc, id_token),
        algorithms=["RS256", "RS384", "RS512", "PS256", "ES256"],
        audience=cfg["client_id"],
        issuer=cfg["issuer"],
        options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        leeway=30,
    )
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise jwt.InvalidTokenError("nonce does not match")
    return claims


# ── Flow ──────────────────────────────────────────────────────────────────────

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _back_to_app(cfg: dict | None, error: str | None = None) -> RedirectResponse:
    base = (cfg or {}).get("public_url", "") + "/"
    resp = RedirectResponse(base + (f"?oidc_error={error}" if error else ""), status_code=303)
    return resp


def start(request: Request):
    cfg = settings()
    if not cfg:
        raise HTTPException(status_code=404, detail="Keycloak sign-in is not switched on")
    try:
        doc = _discovery(cfg["issuer"])
    except Exception as exc:  # Keycloak down or misnamed
        log.warning("OIDC discovery failed: %s", exc)
        return _back_to_app(cfg, "unavailable")
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    now = datetime.utcnow()
    ensure_fork_schema()
    conn = get_db()
    try:
        conn.execute("DELETE FROM oidc_pending WHERE created_at < ?",
                     ((now - timedelta(minutes=PENDING_MINUTES)).isoformat(),))
        conn.execute("INSERT INTO oidc_pending (state, nonce, code_verifier, created_at) VALUES (?,?,?,?)",
                     (state, nonce, verifier, now.isoformat()))
        conn.commit()
    finally:
        conn.close()
    query = urlencode({
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["public_url"] + CALLBACK_PATH,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
    })
    resp = RedirectResponse(f"{doc['authorization_endpoint']}?{query}", status_code=303)
    # Ties the sign-in to this browser, so nobody can finish their own sign-in in someone else's browser.
    resp.set_cookie(STATE_COOKIE, state, max_age=PENDING_MINUTES * 60, httponly=True,
                    secure=_is_secure_request(request), samesite="lax", path="/api/auth/oidc")
    return resp


def _find_or_link_user(conn, cfg: dict, claims: dict) -> tuple[dict | None, str]:
    """The library account for these claims, linking it on first sign-in. Returns (user, error code)."""
    sub = str(claims["sub"])
    row = conn.execute("SELECT user_id FROM oidc_identities WHERE issuer=? AND subject=?",
                       (cfg["issuer"], sub)).fetchone()
    if row:
        user = conn.execute("SELECT * FROM users WHERE id=?", (row["user_id"],)).fetchone()
        if user:
            return dict(user), ""
        # The library account was deleted: forget the old link and look for an account by name below.
        conn.execute("DELETE FROM oidc_identities WHERE user_id=?", (row["user_id"],))

    name = str(claims.get(cfg["username_claim"]) or "").strip()
    if not name or name.lower() in cfg["password_users"]:
        return None, "no_account"
    user = conn.execute("SELECT * FROM users WHERE lower(username)=lower(?)", (name,)).fetchone()
    if not user:
        return None, "no_account"
    if conn.execute("SELECT 1 FROM oidc_identities WHERE user_id=?", (user["id"],)).fetchone():
        return None, "already_linked"  # this library account belongs to another Keycloak person
    conn.execute(
        "INSERT INTO oidc_identities (user_id, issuer, subject, username, linked_at) VALUES (?,?,?,?,?)",
        (user["id"], cfg["issuer"], sub, name, datetime.utcnow().isoformat()),
    )
    log.info("OIDC linked library user %s to %s sub=%s", user["username"], cfg["issuer"], sub)
    return dict(user), ""


def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    cfg = settings()
    if not cfg:
        raise HTTPException(status_code=404, detail="Keycloak sign-in is not switched on")
    if error:  # the person pressed cancel, or Keycloak refused
        _auth_fail(request, reason=f"oidc_{error}"[:60])
        return _back_to_app(cfg, "cancelled")
    cookie_state = request.cookies.get(STATE_COOKIE, "")
    if not code or not state or not cookie_state or not secrets.compare_digest(state, cookie_state):
        _auth_fail(request, reason="oidc_bad_state")
        return _back_to_app(cfg, "expired")

    ensure_fork_schema()
    conn = get_db()
    try:
        pending = conn.execute("SELECT * FROM oidc_pending WHERE state=?", (state,)).fetchone()
        conn.execute("DELETE FROM oidc_pending WHERE state=?", (state,))
        conn.commit()
        if not pending or pending["created_at"] < (datetime.utcnow() - timedelta(minutes=PENDING_MINUTES)).isoformat():
            _auth_fail(request, reason="oidc_expired")
            return _back_to_app(cfg, "expired")
        try:
            doc = _discovery(cfg["issuer"])
            tokens = _exchange_code(cfg, doc, code, pending["code_verifier"])
            claims = _verify_id_token(cfg, doc, tokens.get("id_token", ""), pending["nonce"])
        except Exception as exc:
            log.warning("OIDC sign-in failed: %s", exc)
            _auth_fail(request, reason="oidc_failed")
            return _back_to_app(cfg, "failed")

        user, problem = _find_or_link_user(conn, cfg, claims)
        if not user:
            _auth_fail(request, reason=f"oidc_{problem}", username=str(claims.get(cfg["username_claim"], "")))
            conn.commit()
            return _back_to_app(cfg, problem)

        token = secrets.token_hex(32)
        now = datetime.utcnow()
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_date, expires_at, is_challenge) VALUES (?,?,?,?,0)",
            (token, user["id"], now.isoformat(), (now + timedelta(days=SESSION_LIFETIME_DAYS)).isoformat()),
        )
        conn.execute("UPDATE oidc_identities SET last_login=? WHERE user_id=?", (now.isoformat(), user["id"]))
        conn.commit()
    finally:
        conn.close()

    _auth_ok(request, user["username"])
    resp = _back_to_app(cfg)
    _set_auth_cookies(resp, token, request)
    resp.delete_cookie(STATE_COOKIE, path="/api/auth/oidc")
    return resp


def linked_accounts() -> list[dict]:
    """For the admin: which library accounts are linked to which Keycloak usernames."""
    ensure_fork_schema()
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT u.username AS library_username, o.username AS keycloak_username, o.linked_at, o.last_login "
            "FROM oidc_identities o JOIN users u ON u.id=o.user_id ORDER BY u.username"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def unlink(username: str) -> dict:
    """For the admin: forget a link, so the account is linked again (by username) at its next sign-in."""
    ensure_fork_schema()
    conn = get_db()
    try:
        user = conn.execute("SELECT id FROM users WHERE lower(username)=lower(?)", (username,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="No such user")
        conn.execute("DELETE FROM oidc_identities WHERE user_id=?", (user["id"],))
        conn.commit()
        return {"message": "Unlinked"}
    finally:
        conn.close()
