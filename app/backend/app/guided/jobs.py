"""Background guide builds. Each job runs on the server, so the knitter's iPad can sleep or close the page.

Every progress event is written to the job row as it happens (`last_event`, and `events` without the heartbeats), so
the page can ask at any moment where the build is, including straight after it wakes up. Jobs left running when the
app stopped are started again at start-up. A cancel request is checked between stages and before each model call.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from app.core.foundation import DATA_DIR, get_db
from app.fork_migrations import ensure_fork_schema
from app.guide_builder import ai
from app.guide_builder.pipeline import BuildCancelled, build_guide
from app.guided import settings

log = logging.getLogger("knitting.guided")
MAX_EVENTS = 40
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="guide-build")
_active: set[str] = set()
_active_lock = threading.Lock()


class GuideError(Exception):
    """A problem the knitter can act on. The message is plain English and safe to show."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def recipe_pdf(recipe_id: str):
    return DATA_DIR / recipe_id / "recipe.pdf"


# ---------------------------------------------------------------- views
def job_view(row) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"], "recipe_id": row["recipe_id"], "status": row["status"],
        "created_at": row["created_at"], "started_at": row["started_at"], "finished_at": row["finished_at"],
        "cancel_requested": bool(row["cancel_requested"]),
        "last_event": json.loads(row["last_event"] or "{}"), "events": json.loads(row["events"] or "[]"),
        "error": row["error"], "server_time": _now(),
    }


def latest_job(recipe_id: str) -> dict | None:
    ensure_fork_schema()
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM guide_jobs WHERE recipe_id=? ORDER BY created_at DESC LIMIT 1",
                           (recipe_id,)).fetchone()
        return job_view(row)
    finally:
        conn.close()


def get_guide(recipe_id: str) -> dict | None:
    ensure_fork_schema()
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM guides WHERE recipe_id=?", (recipe_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"recipe_id": row["recipe_id"], "version": row["version"], "built_at": row["built_at"],
            "review_state": row["review_state"], "guide": json.loads(row["guide"])}


# ---------------------------------------------------------------- starting and stopping
def start(recipe_id: str, user: dict) -> dict:
    ensure_fork_schema()
    if not settings.guides_enabled():
        raise GuideError("Guided versions are switched off.", 403)
    conn_cfg = settings.ai_connection()
    if not (conn_cfg["base_url"] and conn_cfg["api_key"]):
        raise GuideError("The AI connection is not set up yet. An admin can add it in Settings, AI.", 400)
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM recipes WHERE id=?", (recipe_id,)).fetchone():
            raise GuideError("That pattern was not found.", 404)
        if not recipe_pdf(recipe_id).exists():
            raise GuideError("This pattern has no PDF to read.", 400)
        busy = conn.execute("SELECT id FROM guide_jobs WHERE recipe_id=? AND status IN ('queued','running')",
                            (recipe_id,)).fetchone()
        if busy:
            raise GuideError("A guided version is already being made for this pattern.", 409)
        job_id = uuid.uuid4().hex
        first = {"stage": "queued", "message": "Waiting to start", "done": 0, "total": 0, "percent": 0,
                 "title": "Waiting to start", "detail": {}, "at": time.time()}
        conn.execute("INSERT INTO guide_jobs (id, recipe_id, status, created_by, created_at, last_event, events) "
                     "VALUES (?, ?, 'queued', ?, ?, ?, '[]')",
                     (job_id, recipe_id, str(user.get("username") or user.get("id") or ""), _now(), json.dumps(first)))
        conn.commit()
    finally:
        conn.close()
    _submit(job_id)
    return latest_job(recipe_id)


def request_cancel(job_id: str) -> dict | None:
    ensure_fork_schema()
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM guide_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise GuideError("That build was not found.", 404)
        if row["status"] == "queued":
            conn.execute("UPDATE guide_jobs SET status='cancelled', cancel_requested=1, finished_at=? WHERE id=?",
                         (_now(), job_id))
        elif row["status"] == "running":
            conn.execute("UPDATE guide_jobs SET cancel_requested=1 WHERE id=?", (job_id,))
        conn.commit()
        return job_view(conn.execute("SELECT * FROM guide_jobs WHERE id=?", (job_id,)).fetchone())
    finally:
        conn.close()


def resume_on_startup() -> None:
    """Jobs that were running when the app stopped start again from the beginning."""
    ensure_fork_schema()
    conn = get_db()
    try:
        conn.execute("UPDATE guide_jobs SET status='queued' WHERE status='running'")
        conn.commit()
        queued = [r["id"] for r in conn.execute("SELECT id FROM guide_jobs WHERE status='queued' ORDER BY created_at")]
    finally:
        conn.close()
    for job_id in queued:
        _submit(job_id)


def _submit(job_id: str) -> None:
    with _active_lock:
        if job_id in _active:
            return
        _active.add(job_id)
    _executor.submit(_run, job_id)


# ---------------------------------------------------------------- running
def _update(job_id: str, **fields) -> None:
    conn = get_db()
    try:
        cols = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE guide_jobs SET {cols} WHERE id=?", (*fields.values(), job_id))
        conn.commit()
    finally:
        conn.close()


def _run(job_id: str) -> None:
    try:
        _run_job(job_id)
    except Exception:  # never let a build take the worker down
        log.exception("guide build %s crashed", job_id)
        _update(job_id, status="failed", finished_at=_now(),
                error="Something went wrong while making the guided version. Try again.")
    finally:
        with _active_lock:
            _active.discard(job_id)


def _run_job(job_id: str) -> None:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM guide_jobs WHERE id=?", (job_id,)).fetchone()
    finally:
        conn.close()
    if row is None or row["status"] != "queued":
        return
    recipe_id = row["recipe_id"]
    _update(job_id, status="running", started_at=_now(), events="[]")
    cfg = settings.ai_connection()
    client = ai.Client(ai.AIConfig(api_key=cfg["api_key"], base_url=cfg["base_url"] or ai.DEFAULT_BASE_URL,
                                   model=cfg["model"]))
    events: list[dict] = []
    lock = threading.Lock()
    cancel_cache = {"at": 0.0, "value": False}

    def cancelled() -> bool:
        if time.time() - cancel_cache["at"] > 1.0:
            c = get_db()
            try:
                r = c.execute("SELECT cancel_requested FROM guide_jobs WHERE id=?", (job_id,)).fetchone()
            finally:
                c.close()
            cancel_cache.update(at=time.time(), value=bool(r and r["cancel_requested"]))
        return cancel_cache["value"]

    def report(event) -> None:
        d = event.as_dict()
        with lock:
            if not d["detail"].get("heartbeat"):
                events.append(d)
                del events[:-MAX_EVENTS]
            _update(job_id, last_event=json.dumps(d), events=json.dumps(events))

    try:
        result = build_guide(str(recipe_pdf(recipe_id)), client, report=report, cancel=cancelled)
    except BuildCancelled:
        _update(job_id, status="cancelled", finished_at=_now())
        return
    except ai.AIError as exc:
        log.warning("guide build %s failed: %s", job_id, exc)
        _update(job_id, status="failed", finished_at=_now(),
                error="The AI service could not read this pattern this time. Try again in a few minutes.")
        return
    finally:
        client.close()
    now = _now()
    conn = get_db()
    try:
        old = conn.execute("SELECT version FROM guides WHERE recipe_id=?", (recipe_id,)).fetchone()
        version = (old["version"] + 1) if old else 1
        conn.execute("INSERT INTO guides (recipe_id, version, guide, job_id, built_at, built_by, review_state, updated_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, 'unchecked', ?) ON CONFLICT(recipe_id) DO UPDATE SET "
                     "version=excluded.version, guide=excluded.guide, job_id=excluded.job_id, built_at=excluded.built_at, "
                     "built_by=excluded.built_by, review_state='unchecked', updated_at=excluded.updated_at",
                     (recipe_id, version, json.dumps(result.guide, ensure_ascii=False), job_id, now, row["created_by"], now))
        conn.execute("UPDATE guide_jobs SET status='done', finished_at=?, report=? WHERE id=?",
                     (now, json.dumps(result.report), job_id))
        conn.commit()
    finally:
        conn.close()
