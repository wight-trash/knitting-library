"""Model facts and reasoning effort for every AI feature. Fork only, see FORK.md "AI tuning".

All AI features use the one model chosen on Settings, AI / Text recognition (`ai_model`). This module adds, per
feature, how hard that model should think (OpenRouter's `reasoning.effort`):

    scan      upstream: reading each page image into text
    cleanup   upstream: the optional second pass that tidies the text
    guide     fork: building a guided version (outline, sections, checks)
    ballband  fork: reading a ball band photo

Which efforts a model offers, its default, whether it takes `temperature`, its output limit and its price come from
OpenRouter's public model list. That list is fetched with httpx (Cloudflare refuses urllib's user agent), at most once
an hour, and only from openrouter.ai: the address typed on the AI page is never fetched from here.

If a saved effort is not one the model offers (the model was changed since), the nearest one it does offer is used;
if the model is unknown or the list cannot be fetched, no effort is sent and the model uses its own default. A
request is never sent with a setting the model would refuse.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from urllib.parse import urlsplit

import httpx

from app.core.foundation import get_db

log = logging.getLogger("knitting.ai_tuning")

FEATURES = ("scan", "cleanup", "guide", "ballband")
# Empty means "the model's own default". Scanning copies text, so it needs little thinking; a guide needs the most.
DEFAULTS = {"scan": "", "cleanup": "", "guide": "high", "ballband": "medium"}
EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")  # weakest to strongest
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
CATALOGUE_TTL = 3600
CATALOGUE_RETRY = 120          # after a failed fetch, wait this long before trying again
MAX_CATALOGUE_BYTES = 16 * 1024 * 1024

# None, not 0: time.monotonic() counts from boot, so on a machine up for under two minutes "now - 0" would look
# like a failure moments ago and the list would never be fetched (seen on a fresh CI runner).
_cache: dict = {"at": None, "failed_at": None, "models": None}
_lock = threading.Lock()
_warned: set[tuple] = set()


def _key(feature: str) -> str:
    return f"fork_effort_{feature}"


# ── Settings ──────────────────────────────────────────────────────────────────

def get_settings() -> dict[str, str]:
    conn = get_db()
    try:
        rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'fork_effort_%'").fetchall()
    finally:
        conn.close()
    saved = {r["key"]: r["value"] for r in rows}
    return {f: saved.get(_key(f), DEFAULTS[f]) for f in FEATURES}


def set_settings(values: dict) -> dict[str, str]:
    clean = {}
    for feature, value in values.items():
        if feature not in FEATURES:
            raise ValueError(f"unknown feature {feature!r}")
        value = str(value or "").strip().lower()
        if value and value not in EFFORTS:
            raise ValueError(f"unknown effort {value!r}")
        clean[feature] = value
    conn = get_db()
    try:
        for feature, value in clean.items():
            conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (_key(feature), value))
        conn.commit()
    finally:
        conn.close()
    return get_settings()


def ai_page_settings() -> dict[str, str]:
    """The model and connection from the AI / Text recognition page."""
    conn = get_db()
    try:
        rows = conn.execute("SELECT key, value FROM app_settings WHERE key IN "
                            "('ai_base_url', 'ai_api_key', 'ai_model', 'ai_timeout', 'ai_max_output_tokens')").fetchall()
    finally:
        conn.close()
    return {r["key"]: r["value"] or "" for r in rows}


# ── OpenRouter's model list ───────────────────────────────────────────────────

def is_openrouter(base_url: str | None) -> bool:
    try:
        host = urlsplit(str(base_url or "").strip()).hostname or ""
    except ValueError:
        return False
    return host == "openrouter.ai"


def _fetch_catalogue() -> dict[str, dict]:
    r = httpx.get(OPENROUTER_MODELS_URL, timeout=20, follow_redirects=False, headers={"Accept": "application/json"})
    r.raise_for_status()
    if len(r.content) > MAX_CATALOGUE_BYTES:
        raise ValueError("model list is too large")
    data = r.json().get("data")
    if not isinstance(data, list):
        raise ValueError("model list has no data")
    return {m["id"]: m for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)}


def catalogue(refresh: bool = False) -> dict[str, dict] | None:
    """OpenRouter's models by id, cached for an hour. None if it has never been fetched successfully."""
    now = time.monotonic()
    with _lock:
        fresh = _cache["models"] is not None and _cache["at"] is not None and now - _cache["at"] < CATALOGUE_TTL
        backing_off = _cache["failed_at"] is not None and now - _cache["failed_at"] < CATALOGUE_RETRY
        if (fresh and not refresh) or (backing_off and not refresh):
            return _cache["models"]
    try:
        models = _fetch_catalogue()
    except Exception as exc:  # network, Cloudflare, a changed format: keep what we had
        log.warning("OpenRouter model list could not be fetched (%s): %s", type(exc).__name__, str(exc)[:200])
        with _lock:
            _cache["failed_at"] = now
            return _cache["models"]
    with _lock:
        _cache.update(at=now, failed_at=None, models=models)
    return models


def _per_million(value) -> float | None:
    try:
        return round(float(value) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None


def model_info(model_id: str) -> dict | None:
    """What the page and the requests need to know about one model, or None if OpenRouter does not list it."""
    models = catalogue()
    m = (models or {}).get(str(model_id or "").strip())
    if not m:
        return None
    params = set(m.get("supported_parameters") or [])
    reasoning = m.get("reasoning") or {}
    efforts = [e for e in EFFORTS if e in (reasoning.get("supported_efforts") or [])]
    can_reason = "reasoning" in params or bool(efforts)
    defaults = m.get("default_parameters") or {}
    top = m.get("top_provider") or {}
    pricing = m.get("pricing") or {}
    inputs = (m.get("architecture") or {}).get("input_modalities") or []
    return {
        "id": m["id"],
        "name": m.get("name") or m["id"],
        "image_input": "image" in inputs,
        "structured_outputs": "structured_outputs" in params,
        "temperature": "temperature" in params,
        "default_temperature": defaults.get("temperature"),
        "reasoning": {
            "supported": can_reason,
            "efforts": efforts,
            "default": reasoning.get("default_effort") or "",
            "mandatory": bool(reasoning.get("mandatory")),
        },
        "max_output_tokens": top.get("max_completion_tokens"),
        "context_length": m.get("context_length") or top.get("context_length"),
        "price_in": _per_million(pricing.get("prompt")),
        "price_out": _per_million(pricing.get("completion")),
    }


# ── What a request gets ───────────────────────────────────────────────────────

def nearest_effort(want: str, offered: list[str]) -> str | None:
    """The offered effort closest to `want` (ties go to the stronger one). "none" is only chosen if asked for."""
    if want in offered:
        return want
    choices = [e for e in offered if e != "none"] or offered
    if not choices or want not in EFFORTS:
        return None
    rank = EFFORTS.index(want)
    return min(choices, key=lambda e: (abs(EFFORTS.index(e) - rank), -EFFORTS.index(e)))


def effective_effort(feature: str, base_url: str | None, model: str | None) -> str | None:
    """The effort to send for this feature and model, or None to send none (the model's own default)."""
    want = get_settings().get(feature, "")
    if not want or not is_openrouter(base_url) or not model:
        return None
    info = model_info(model)
    if info is None or not info["reasoning"]["supported"]:
        return None
    offered = info["reasoning"]["efforts"]
    if not offered:  # reasons, but OpenRouter lists no levels (some Qwen and Gemma models): leave it to the model
        return None
    chosen = nearest_effort(want, offered)
    if chosen != want and (feature, model, want) not in _warned:
        _warned.add((feature, model, want))
        log.warning("%s effort %r is not offered by %s; using %r", feature, want, model, chosen)
    return chosen


def request_extras(cfg: dict, feature: str) -> dict:
    """Extra fields for a chat/completions body built from the AI page's settings (upstream's scan and cleanup)."""
    try:
        effort = effective_effort(feature, cfg.get("ai_base_url"), cfg.get("ai_model"))
    except Exception as exc:  # tuning must never stop a transcription
        log.warning("AI tuning skipped for %s (%s)", feature, type(exc).__name__)
        return {}
    return {"reasoning": {"effort": effort}} if effort else {}


async def request_extras_async(cfg: dict, feature: str) -> dict:
    # The model list may need fetching; keep that off the event loop.
    return await asyncio.to_thread(request_extras, cfg, feature)


def prompts() -> list[dict]:
    """The fork's prompts, read-only, for the AI page."""
    from app.guide_builder import prompts as gp
    from app.stash import ballband
    return [
        {"id": "guide_outline", "title": "Guided version: outline", "text": gp.OUTLINE},
        {"id": "guide_section", "title": "Guided version: each section", "text": gp.SECTION},
        {"id": "guide_picture", "title": "Guided version: pages without text", "text": gp.PICTURE},
        {"id": "ballband", "title": "Ball band photo", "text": ballband.SYSTEM},
    ]
