"""The fork's settings, stored as extra rows in upstream's app_settings table (keys start with fork_)."""
from __future__ import annotations

from app.core.foundation import get_db

DEFAULT_GUIDE_MODEL = "anthropic/claude-haiku-5.5"
KEYS = {
    "fork_feature_guides": "false",          # feature switch: the Guided tab and building guides
    "fork_guide_model": DEFAULT_GUIDE_MODEL,  # old: only used while the AI page has no model (see ai_connection)
}


def get_all() -> dict[str, str]:
    conn = get_db()
    try:
        rows = conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'fork_%'").fetchall()
    finally:
        conn.close()
    out = dict(KEYS)
    out.update({r["key"]: r["value"] for r in rows if r["key"] in KEYS})
    return out


def set_values(values: dict[str, str]) -> dict[str, str]:
    conn = get_db()
    try:
        for key, value in values.items():
            if key in KEYS:
                conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
        conn.commit()
    finally:
        conn.close()
    return get_all()


def guides_enabled() -> bool:
    return get_all()["fork_feature_guides"].strip().lower() in ("1", "true", "yes", "on")


def ai_connection() -> dict:
    """Base URL, key, model and timeout from the app's own AI settings page (Settings, AI / Text recognition).

    The fork used to keep its own model (`fork_guide_model`). It is only used now if the AI page has no model yet,
    so a library set up before this change keeps working until a model is chosen there."""
    conn = get_db()
    try:
        rows = conn.execute("SELECT key, value FROM app_settings WHERE key IN "
                            "('ai_base_url', 'ai_api_key', 'ai_model', 'ai_timeout')").fetchall()
    finally:
        conn.close()
    cfg = {r["key"]: r["value"] or "" for r in rows}
    try:
        timeout = min(max(float(cfg.get("ai_timeout") or 600), 60.0), 1800.0)
    except ValueError:
        timeout = 600.0
    model = cfg.get("ai_model", "").strip() or get_all()["fork_guide_model"] or DEFAULT_GUIDE_MODEL
    return {"base_url": (cfg.get("ai_base_url") or "").rstrip("/"), "api_key": cfg.get("ai_api_key") or "",
            "model": model, "timeout": timeout, "model_from_ai_page": bool(cfg.get("ai_model", "").strip())}
