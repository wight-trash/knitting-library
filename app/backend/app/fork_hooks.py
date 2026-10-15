"""Calls from upstream code into the fork. Each upstream call site is one line marked `# fork: ... (FORK.md)`.

The upstream bug fixes (staged imports in the library list, deleting sessions or recipes that used stock) are at the
end of this file.

after_quantity_change() keeps the stash in grams (app/stash/) in step when upstream changes a yarn item's whole-ball
count: the +1/-1 buttons (adjust_inventory), creating an item with a quantity, editing an item, and starting a
project that uses balls from the stash.

Transactions: the hook is called with the caller's connection, *before* the caller commits. Its rows go into the
caller's transaction inside a SAVEPOINT, so the new ball count and the gram history are committed together or not at
all. If the hook fails, it rolls back to its savepoint (so none of its own rows are left half-written), logs the
problem and returns; the upstream change then commits on its own, and the stash catches up the next time the item is
read (rules 2 and 4 in docs/guided-knitting/PHASE2-STASH.md). Calling it after the commit with its own transaction
was the other option, but a crash between the two commits would leave the counts apart, and opening a second
connection while the caller still holds the write lock would wait on that lock.

The hook never raises into upstream code. It does nothing when the change came from the stash module itself (the
stash module sets the quantity with its own SQL, and also marks its work with stash_writing(), so nothing is counted
twice).
"""
from __future__ import annotations

import contextvars
import logging
import sqlite3
from contextlib import contextmanager

log = logging.getLogger("knitting.fork.stash")
_stash_writing: contextvars.ContextVar[bool] = contextvars.ContextVar("fork_stash_writing", default=False)


@contextmanager
def stash_writing():
    """Marks changes made by the stash module itself; the hook ignores them."""
    token = _stash_writing.set(True)
    try:
        yield
    finally:
        _stash_writing.reset(token)


def after_quantity_change(conn: sqlite3.Connection, item_id: str, old_qty, new_qty, reason: str,
                          created_by: str = "", project_session_id: str | None = None) -> None:
    """Upstream changed inventory_items.quantity for `item_id` from old_qty to new_qty (not yet committed).

    new_qty may be None: the hook then reads the item's quantity on `conn`. `reason` is one of create, adjust, edit,
    project_start and only shapes the note in the history.
    """
    if _stash_writing.get():
        return
    try:
        from app.stash import ledger
        ledger.follow_upstream_change(conn, item_id, old_qty, new_qty, reason, created_by or "", project_session_id)
    except Exception:  # never let the stash break the inventory
        log.exception("stash hook failed for inventory item %s; the stash catches up on its next read", item_id)


# ---------------------------------------------------------------- upstream bugs fixed in the fork (FORK.md)
# Upstream keeps unconfirmed import-wizard drafts as ordinary `recipes` rows, with an `import_queue` row marked
# 'staged', and its library list did not leave them out. list_recipes() adds this to its WHERE clause.
HIDE_STAGED_IMPORTS_SQL = " AND r.id NOT IN (SELECT recipe_id FROM import_queue WHERE status='staged')"


def before_sessions_delete(conn: sqlite3.Connection, recipe_id: str, session_id: str | None = None,
                           user_id: str | None = None) -> None:
    """Upstream is about to delete project sessions of `recipe_id` (one session, one user's, or all of them).

    inventory_log.session_id has a foreign key to project_sessions, so a session that took balls from the stash
    could not be deleted (500). The stock history keeps its rows (the balls were used, and the item's count still
    shows it; the note still names the pattern); only the link to the deleted session is cleared. Same transaction
    as the caller. The fork's stash_ledger keeps its plain session id (no foreign key), which is harmless.
    """
    if session_id is not None:
        where, params = "recipe_id=? AND id=?", (recipe_id, session_id)
    elif user_id is not None:
        where, params = "recipe_id=? AND user_id=?", (recipe_id, user_id)
    else:
        where, params = "recipe_id=?", (recipe_id,)
    try:
        conn.execute("UPDATE inventory_log SET session_id=NULL WHERE session_id IN "
                     f"(SELECT id FROM project_sessions WHERE {where})", params)
    except Exception:  # the upstream delete then fails as it did before; nothing else is changed
        log.exception("could not unlink the stock history from the sessions of recipe %s", recipe_id)


def before_recipe_delete(conn: sqlite3.Connection, recipe_id: str) -> None:
    """Upstream is about to delete recipe `recipe_id` and its sessions (same transaction, before the deletes).

    Stock history: as before_sessions_delete, and the link to the recipe is cleared too (inventory_log.recipe_id
    also has a foreign key). Guides: the fork's guide and finished build rows for the recipe go, and a build still
    waiting or running is cancelled. They have no foreign key, and recipe ids are made from the title, so a new
    pattern with the same title would otherwise pick up the old pattern's guide.
    """
    before_sessions_delete(conn, recipe_id)
    try:
        conn.execute("UPDATE inventory_log SET recipe_id=NULL WHERE recipe_id=?", (recipe_id,))
    except Exception:
        log.exception("could not unlink the stock history from recipe %s", recipe_id)
    try:
        conn.execute("SAVEPOINT fork_forget_guide")
        try:
            conn.execute("DELETE FROM guides WHERE recipe_id=?", (recipe_id,))
            conn.execute("UPDATE guide_jobs SET cancel_requested=1 WHERE recipe_id=? AND status='running'", (recipe_id,))
            conn.execute("DELETE FROM guide_jobs WHERE recipe_id=? AND status!='running'", (recipe_id,))
            conn.execute("RELEASE SAVEPOINT fork_forget_guide")
        except Exception:
            conn.execute("ROLLBACK TO SAVEPOINT fork_forget_guide")
            conn.execute("RELEASE SAVEPOINT fork_forget_guide")
            raise
    except Exception:  # never let the guides stop a recipe being deleted
        log.exception("could not remove the guide rows of recipe %s", recipe_id)


def refuse_yarn_delete_if_used(conn, yarn_id: str, colour_id: str | None = None) -> None:
    """Upstream deletes yarns and colours without checking what uses them. A yarn or colour that is in the stash or
    was used in a project is referenced by a foreign key, so the delete failed with an error and left the database
    locked for minutes (every page then failed). Refuse with a plain message instead, before anything is written.
    Closes the caller's connection when refusing, because the upstream function has no try/finally."""
    from fastapi import HTTPException

    if colour_id:
        used = conn.execute("SELECT 1 FROM inventory_items WHERE yarn_colour_id=? LIMIT 1", (colour_id,)).fetchone() or \
            conn.execute("SELECT 1 FROM project_sessions WHERE yarn_colour_id=? LIMIT 1", (colour_id,)).fetchone()
        what = "colour"
    else:
        used = conn.execute("SELECT 1 FROM inventory_items WHERE yarn_id=? LIMIT 1", (yarn_id,)).fetchone() or \
            conn.execute("SELECT 1 FROM project_sessions WHERE yarn_id=? LIMIT 1", (yarn_id,)).fetchone()
        what = "yarn"
    if used:
        conn.close()
        raise HTTPException(status_code=409, detail=f"This {what} can't be deleted because it is in your stash or was "
                                                    f"used in a project. Remove it from the stash first.")
