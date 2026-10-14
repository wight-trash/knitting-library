"""The fork's settings, stored as extra rows in upstream's app_settings table (keys start with fork_)."""
from __future__ import annotations

from app.core.foundation import get_db

DEFAULT_GUIDE_MODEL = "anthropic/claude-haiku-5.5"
KEYS = {
    "fork_feature_guides": "false",          # feature switch: the Guided tab and building guides
    "fork_guide_model": DEFAULT_GUIDE_MODEL,  # model used to build guides (the app's AI settings give URL and key)
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
    """Base URL and key from the app's own AI settings page; the model from the fork's setting."""
    conn = get_db()
    try:
        rows = conn.execute("SELECT key, value FROM app_settings WHERE key IN ('ai_base_url', 'ai_api_key')").fetchall()
    finally:
        conn.close()
    cfg = {r["key"]: r["value"] for r in rows}
    return {"base_url": (cfg.get("ai_base_url") or "").rstrip("/"), "api_key": cfg.get("ai_api_key") or "",
            "model": get_all()["fork_guide_model"] or DEFAULT_GUIDE_MODEL}
