"""Database tables owned by this fork (wight-trash/knitting-library), kept apart from upstream's schema code.

Version 1: guided knitting (guide_jobs, guides). Version 2: the stash in grams (yarn_specs, stash_ledger), see
docs/guided-knitting/PHASE2-STASH.md.

Upstream builds its schema in app/core/foundation.py. The fork never edits that: it adds its own tables here, with
CREATE TABLE IF NOT EXISTS, and records its own schema version in app_settings (key `fork_schema_version`). No
foreign keys point at upstream tables, because upstream deletes rows (recipes, project sessions) directly.

ensure_fork_schema() is safe to call any number of times; the guided module calls it at start-up and before use.
"""
from __future__ import annotations

import sqlite3
import threading

FORK_SCHEMA_VERSION = 2
_done = False
_lock = threading.Lock()

MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE IF NOT EXISTS guide_jobs (
        id            TEXT PRIMARY KEY,
        recipe_id     TEXT NOT NULL,
        status        TEXT NOT NULL,          -- queued, running, done, failed, cancelled
        created_by    TEXT NOT NULL DEFAULT '',
        created_at    TEXT NOT NULL,
        started_at    TEXT,
        finished_at   TEXT,
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        last_event    TEXT NOT NULL DEFAULT '{}',   -- the latest progress event (JSON)
        events        TEXT NOT NULL DEFAULT '[]',   -- recent progress events (JSON list, heartbeats left out)
        error         TEXT NOT NULL DEFAULT '',
        report        TEXT NOT NULL DEFAULT '{}'    -- usage, timings and problems from the builder (JSON)
    );
    CREATE INDEX IF NOT EXISTS idx_guide_jobs_recipe ON guide_jobs (recipe_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_guide_jobs_status ON guide_jobs (status);

    CREATE TABLE IF NOT EXISTS guides (
        recipe_id     TEXT PRIMARY KEY,
        version       INTEGER NOT NULL DEFAULT 1,
        guide         TEXT NOT NULL,            -- the guide, format 0.2 (JSON)
        job_id        TEXT NOT NULL DEFAULT '',
        built_at      TEXT NOT NULL,
        built_by      TEXT NOT NULL DEFAULT '',
        review_state  TEXT NOT NULL DEFAULT 'unchecked',   -- unchecked, checked
        updated_at    TEXT NOT NULL
    );
    """,
    2: """
    CREATE TABLE IF NOT EXISTS yarn_specs (
        yarn_id          TEXT PRIMARY KEY,        -- upstream yarns.id (no foreign key)
        grams_per_ball   REAL,
        metres_per_ball  REAL,
        weight           TEXT,                    -- as the knitter or band says: "DK", "Aran", "DROPS group B"
        weight_category  INTEGER,                 -- Craft Yarn Council 0-7 when known
        fibre            TEXT,
        needle_mm_min    REAL,
        needle_mm_max    REAL,
        gauge_stitches   REAL,
        gauge_rows       REAL,
        gauge_over_cm    REAL,
        care             TEXT,
        source           TEXT NOT NULL DEFAULT 'manual',   -- manual, ball_band, shop_link
        updated_at       TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS stash_ledger (
        id                 TEXT PRIMARY KEY,
        item_id            TEXT NOT NULL,         -- upstream inventory_items.id (type 'yarn'), no foreign key
        change_g           REAL NOT NULL,         -- + adds, - removes
        reason             TEXT NOT NULL,         -- opening, purchase, correction, ball_count, project_reserve,
                                                  -- project_release, project_use, leftover
        project_session_id TEXT,                  -- for Phase 6
        note               TEXT NOT NULL DEFAULT '',
        created_at         TEXT NOT NULL,
        created_by         TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_stash_ledger_item ON stash_ledger (item_id, created_at);
    """,
}


def _current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM app_settings WHERE key='fork_schema_version'").fetchone()
    try:
        return int(row[0]) if row else 0
    except (TypeError, ValueError):
        return 0


def ensure_fork_schema(conn: sqlite3.Connection | None = None) -> None:
    """Bring the fork's tables up to FORK_SCHEMA_VERSION. Cheap after the first call in a process."""
    global _done
    if _done and conn is None:
        return
    with _lock:
        own = conn is None
        if own:
            from app.core.foundation import get_db
            conn = get_db()
        try:
            version = _current_version(conn)
            for target in sorted(MIGRATIONS):
                if target > version:
                    conn.executescript(MIGRATIONS[target])
                    conn.execute("INSERT INTO app_settings (key, value) VALUES ('fork_schema_version', ?) "
                                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(target),))
                    conn.commit()
            _done = True
        finally:
            if own:
                conn.close()
