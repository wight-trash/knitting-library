"""Calls from upstream code into the fork. Each upstream call site is one line marked `# fork: stash (FORK.md)`.

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
