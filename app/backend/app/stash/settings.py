"""The stash switch, stored like the guided settings: a fork_ row in upstream's app_settings table."""
from __future__ import annotations

import sqlite3

from app.core.foundation import get_db

KEY = "fork_feature_stash"   # feature switch: "Stash in grams" (off by default)
DEFAULT = "false"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def stash_enabled(conn: sqlite3.Connection | None = None) -> bool:
    """Whether the stash in grams is switched on. Pass a connection to read inside its transaction (the hook does)."""
    own = conn is None
    if own:
        conn = get_db()
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (KEY,)).fetchone()
    finally:
        if own:
            conn.close()
    return _truthy(row[0] if row else DEFAULT)


def set_enabled(enabled: bool) -> bool:
    conn = get_db()
    try:
        conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (KEY, "true" if enabled else "false"))
        conn.commit()
    finally:
        conn.close()
    return stash_enabled()
