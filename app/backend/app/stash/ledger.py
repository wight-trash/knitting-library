"""The stash in grams: yarn ball details, the gram history (stash_ledger) and the whole-ball count kept in step.

Rules (docs/guided-knitting/PHASE2-STASH.md):
1. Stock in grams is the sum of an item's ledger rows; balls = grams / grams_per_ball.
2. The first time an item is read with grams_per_ball known and no ledger rows, an `opening` row of
   quantity x grams_per_ball is written.
3. Without grams_per_ball the item stays in whole balls.
4. After every ledger change, inventory_items.quantity = whole balls, rounded down.
5. Upstream changes to the count arrive through fork_hooks.after_quantity_change (follow_upstream_change here).
6. Corrections write the difference, never overwrite.
7. The stash belongs to the household; created_by records who made each change.

If the whole-ball count was changed while the ledger could not follow (the switch was off, or the yarn had no ball
weight), the next read adds a `ball_count` row so that the two agree again; the ball count wins, because that is what
the knitter has been looking at.
"""
from __future__ import annotations

import datetime as dt
import math
import sqlite3
import uuid

from app import fork_hooks
from app.core.foundation import get_db
from app.fork_migrations import ensure_fork_schema
from app.guide_builder.units import parse_number
from app.stash import settings

EPS = 1e-6
REASONS = ("opening", "purchase", "correction", "ball_count", "project_reserve", "project_release", "project_use",
           "leftover")
SOURCES = ("manual", "ball_band", "shop_link")
MAX_BALLS = 1000
MAX_GRAMS = 100_000


class StashError(Exception):
    """A problem the knitter can act on. The message is plain English and safe to show."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def _user_name(user: dict | None) -> str:
    user = user or {}
    return str(user.get("username") or user.get("id") or "")


def _close(conn: sqlite3.Connection) -> None:
    """Close a connection this module opened, undoing anything left uncommitted after an error."""
    if conn.in_transaction:
        conn.rollback()
    conn.close()


def tables_ready(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='stash_ledger'").fetchone() is not None


def require_enabled() -> None:
    ensure_fork_schema()
    if not settings.stash_enabled():
        raise StashError("The stash in grams is switched off. An admin can switch it on in Settings, Knitting upgrades.",
                         403)


# ---------------------------------------------------------------- numbers
def number(value, label: str, *, low: float = 0.0, high: float = MAX_GRAMS, allow_zero: bool = False) -> float | None:
    """A number from a form: 50, 4.5, "4,5" or "4½". None when empty. Raises StashError with a plain message."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise StashError(f"{label} should be a number.")
    if isinstance(value, (int, float)):
        out = float(value)
    else:
        out = parse_number(str(value))
        if out is None:
            raise StashError(f"{label} should be a number.")
    if math.isnan(out) or math.isinf(out):
        raise StashError(f"{label} should be a number.")
    too_low = out < low or (out == low and not allow_zero)
    if too_low or out > high:
        lowest = f"{low:g} or more" if allow_zero else f"more than {low:g}"
        raise StashError(f"{label} should be {lowest} and at most {high:g}.")
    return out


GRAM_SLACK = 0.05   # ledger rows are kept to 0.01 g; this absorbs their rounding when counting balls


def whole_balls(grams: float, gpb: float) -> int:
    return max(0, math.floor((grams + GRAM_SLACK) / gpb))


def balls_shown(grams: float, gpb: float) -> float:
    """Balls to one decimal, rounded down, so 4.97 balls shows as 4.9 next to a count of 4 (never "5.0")."""
    return max(0.0, math.floor((grams + GRAM_SLACK) / gpb * 10) / 10)


# ---------------------------------------------------------------- yarn specs
SPEC_NUMBERS = {  # field: (label for messages, lowest, highest)
    "grams_per_ball": ("The ball weight in grams", 0, 5000),
    "metres_per_ball": ("The length in metres", 0, 100_000),
    "needle_mm_min": ("The needle size in mm", 0, 50),
    "needle_mm_max": ("The needle size in mm", 0, 50),
    "gauge_stitches": ("The number of stitches", 0, 200),
    "gauge_rows": ("The number of rows", 0, 400),
    "gauge_over_cm": ("The tension width in cm", 0, 100),
}
SPEC_TEXTS = {"weight": 60, "fibre": 200, "care": 500}
SPEC_FIELDS = (*SPEC_NUMBERS, "weight_category", *SPEC_TEXTS, "source")


def spec_view(row) -> dict | None:
    if row is None:
        return None
    return {"yarn_id": row["yarn_id"], **{k: row[k] for k in SPEC_FIELDS}, "updated_at": row["updated_at"]}


def _spec_row(conn: sqlite3.Connection, yarn_id: str | None):
    if not yarn_id:
        return None
    return conn.execute("SELECT * FROM yarn_specs WHERE yarn_id=?", (yarn_id,)).fetchone()


def _gpb(spec_row) -> float | None:
    if spec_row is None or spec_row["grams_per_ball"] is None:
        return None
    value = float(spec_row["grams_per_ball"])
    return value if value > 0 else None


def get_spec(yarn_id: str) -> dict:
    require_enabled()
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM yarns WHERE id=?", (yarn_id,)).fetchone():
            raise StashError("That yarn was not found.", 404)
        return {"yarn_id": yarn_id, "spec": spec_view(_spec_row(conn, yarn_id))}
    finally:
        conn.close()


def _clean_spec(body: dict, old: dict | None) -> dict:
    out = dict(old or {k: None for k in SPEC_FIELDS})
    if not old:
        out["source"] = "manual"
    for key, (label, low, high) in SPEC_NUMBERS.items():
        if key in body:
            value = number(body[key], label, low=low, high=high)
            out[key] = round(value, 2) if value is not None else None
    if "weight_category" in body:
        value = number(body["weight_category"], "The yarn weight number", low=0, high=7, allow_zero=True)
        if value is not None and value != int(value):
            raise StashError("The yarn weight number should be a whole number from 0 to 7.")
        out["weight_category"] = int(value) if value is not None else None
    for key, limit in SPEC_TEXTS.items():
        if key in body:
            text = str(body[key] or "").strip()
            if len(text) > limit:
                raise StashError(f"That is too long for {key}: keep it under {limit} letters.")
            out[key] = text or None
    if "source" in body:
        source = str(body["source"] or "manual")
        if source not in SOURCES:
            raise StashError("Unknown source for the ball details.")
        out["source"] = source
    lo, hi = out.get("needle_mm_min"), out.get("needle_mm_max")
    if lo is not None and hi is not None and lo > hi:
        out["needle_mm_min"], out["needle_mm_max"] = hi, lo
    elif lo is not None and hi is None:
        out["needle_mm_max"] = lo
    elif hi is not None and lo is None:
        out["needle_mm_min"] = hi
    return out


def save_spec(yarn_id: str, body: dict, user: dict) -> dict:
    """Save a yarn's ball details (only the fields given; null clears one). If the ball weight changes, the stash
    of that yarn keeps its ball count and the history gets a correction explaining the new grams."""
    require_enabled()
    if not isinstance(body, dict):
        raise StashError("Nothing to save.")
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT 1 FROM yarns WHERE id=?", (yarn_id,)).fetchone():
            raise StashError("That yarn was not found.", 404)
        old_row = _spec_row(conn, yarn_id)
        old = spec_view(old_row)
        new = _clean_spec(body, old)
        cols = ", ".join(SPEC_FIELDS)
        marks = ", ".join("?" for _ in SPEC_FIELDS)
        updates = ", ".join(f"{k}=excluded.{k}" for k in SPEC_FIELDS)
        conn.execute(f"INSERT INTO yarn_specs (yarn_id, {cols}, updated_at) VALUES (?, {marks}, ?) "
                     f"ON CONFLICT(yarn_id) DO UPDATE SET {updates}, updated_at=excluded.updated_at",
                     (yarn_id, *[new[k] for k in SPEC_FIELDS], _now()))
        old_gpb, new_gpb = _gpb(old_row), new["grams_per_ball"]
        if old_gpb and new_gpb and abs(old_gpb - new_gpb) > EPS:
            _rescale_items(conn, yarn_id, old_gpb, new_gpb, _user_name(user))
        conn.commit()
        return {"yarn_id": yarn_id, "spec": spec_view(_spec_row(conn, yarn_id))}
    finally:
        _close(conn)


def _rescale_items(conn, yarn_id: str, old_gpb: float, new_gpb: float, created_by: str) -> None:
    items = conn.execute("SELECT * FROM inventory_items WHERE type='yarn' AND yarn_id=?", (yarn_id,)).fetchall()
    for item in items:
        total, count = _stock(conn, item["id"])
        if not count:
            continue  # its opening balance is written with the new ball weight on the next read
        _reconcile(conn, item, old_gpb, item["quantity"], created_by)
        total, _ = _stock(conn, item["id"])
        target = total / old_gpb * new_gpb
        _append(conn, item["id"], target - total, "correction",
                f"Ball weight changed from {old_gpb:g} g to {new_gpb:g} g; the number of balls stays the same",
                created_by)
        _sync_quantity(conn, item["id"], new_gpb)


# ---------------------------------------------------------------- ledger
def _stock(conn, item_id: str) -> tuple[float, int]:
    row = conn.execute("SELECT COALESCE(SUM(change_g), 0) AS g, COUNT(*) AS n FROM stash_ledger WHERE item_id=?",
                       (item_id,)).fetchone()
    return float(row[0]), int(row[1])


def _append(conn, item_id: str, change_g: float, reason: str, note: str, created_by: str,
            project_session_id: str | None = None) -> str | None:
    change_g = round(change_g, 2)
    if abs(change_g) < 0.005 and reason != "opening":
        return None
    row_id = uuid.uuid4().hex
    conn.execute("INSERT INTO stash_ledger (id, item_id, change_g, reason, project_session_id, note, created_at, "
                 "created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (row_id, item_id, change_g, reason, project_session_id, note[:300], _now(), created_by))
    return row_id


def _sync_quantity(conn, item_id: str, gpb: float) -> int:
    total, _ = _stock(conn, item_id)
    qty = whole_balls(total, gpb)
    with fork_hooks.stash_writing():
        conn.execute("UPDATE inventory_items SET quantity=? WHERE id=? AND quantity<>?", (qty, item_id, qty))
    return qty


def _balls_text(n: float) -> str:
    return f"{n:g} ball" + ("" if abs(n) == 1 else "s")


def _reconcile(conn, item, gpb: float, believed_qty: int, created_by: str) -> None:
    """Opening balance (rule 2), or a catch-up row when the ball count was changed while grams were not kept."""
    total, count = _stock(conn, item["id"])
    if count == 0:
        if believed_qty > 0:
            _append(conn, item["id"], believed_qty * gpb, "opening",
                    f"Opening balance: {_balls_text(believed_qty)} of {gpb:g} g", created_by)
        return
    counted = whole_balls(total, gpb)
    if counted != believed_qty:
        _append(conn, item["id"], (believed_qty - counted) * gpb, "ball_count",
                f"Matched to the ball count of {believed_qty}, which changed while grams were not being kept",
                created_by)


def _upstream_log(conn, item_id: str, change: int, reason: str, note: str) -> None:
    """Keep upstream's own history (inventory_log) explaining the whole-ball count."""
    if change:
        conn.execute("INSERT INTO inventory_log (id, item_id, change, reason, note, created_at) VALUES (?,?,?,?,?,?)",
                     (str(uuid.uuid4()), item_id, change, reason, note[:300], dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat()))


_HOOK_NOTES = {
    "create": lambda old, new: f"New stash item: {_balls_text(new)}",
    "adjust": lambda old, new: f"{'+' if new > old else '−'}{_balls_text(abs(new - old))} with the ball count buttons",
    "edit": lambda old, new: f"Ball count edited from {old} to {new}",
    "project_start": lambda old, new: f"{_balls_text(old - new)} taken for a project",
}


def follow_upstream_change(conn, item_id: str, old_qty, new_qty, reason: str, created_by: str,
                           project_session_id: str | None) -> None:
    """Called by fork_hooks.after_quantity_change inside the caller's transaction (see fork_hooks for why)."""
    if not tables_ready(conn) or not settings.stash_enabled(conn):
        return
    item = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    if item is None or item["type"] != "yarn":
        return
    gpb = _gpb(_spec_row(conn, item["yarn_id"]))
    if not gpb:
        return  # rule 3: whole balls only
    old_qty = int(old_qty or 0)
    new_qty = int(item["quantity"] if new_qty is None else new_qty)
    conn.execute("SAVEPOINT fork_stash")
    try:
        _reconcile(conn, item, gpb, old_qty, created_by)
        if new_qty != old_qty:
            note = _HOOK_NOTES.get(reason, lambda o, n: f"Ball count changed from {o} to {n}")(old_qty, new_qty)
            total, _ = _stock(conn, item_id)
            change = max((new_qty - old_qty) * gpb, -total)  # never below nothing
            _append(conn, item_id, change, "ball_count", note, created_by, project_session_id)
        _sync_quantity(conn, item_id, gpb)
    except Exception:
        conn.execute("ROLLBACK TO fork_stash")
        conn.execute("RELEASE fork_stash")
        raise
    conn.execute("RELEASE fork_stash")


# ---------------------------------------------------------------- reading
def _item_view(conn, item, created_by: str) -> dict:
    """One yarn item with grams and balls. Writes the opening balance or a catch-up row when needed."""
    spec_row = _spec_row(conn, item["yarn_id"])
    gpb = _gpb(spec_row)
    yarn = conn.execute("SELECT name FROM yarns WHERE id=?", (item["yarn_id"],)).fetchone() if item["yarn_id"] else None
    colour = (conn.execute("SELECT name, image_path FROM yarn_colours WHERE id=?", (item["yarn_colour_id"],)).fetchone()
              if item["yarn_colour_id"] else None)
    out = {
        "id": item["id"], "name": item["name"], "yarn_id": item["yarn_id"], "yarn_colour_id": item["yarn_colour_id"],
        "yarn_name": yarn["name"] if yarn else "", "colour_name": colour["name"] if colour else "",
        "colour_image_path": colour["image_path"] if colour else "",
        "spec": spec_view(spec_row), "mode": "balls", "grams": None, "balls": None,
    }
    if gpb:
        _reconcile(conn, item, gpb, item["quantity"], created_by)
        total, _ = _stock(conn, item["id"])
        qty = _sync_quantity(conn, item["id"], gpb)
        out.update(mode="grams", grams=round(total, 1), balls=balls_shown(total, gpb), quantity=qty)
    else:
        out["quantity"] = item["quantity"]
    return out


def _yarn_item(conn, item_id: str):
    item = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
    if item is None or item["type"] != "yarn":
        raise StashError("That yarn is not in the stash.", 404)
    return item


def _ledger(conn, item_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM stash_ledger WHERE item_id=? ORDER BY created_at, rowid", (item_id,)).fetchall()
    out, balance = [], 0.0
    for r in rows:
        balance += r["change_g"]
        out.append({"id": r["id"], "change_g": r["change_g"], "reason": r["reason"], "note": r["note"],
                    "project_session_id": r["project_session_id"], "created_at": r["created_at"],
                    "created_by": r["created_by"], "balance_g": round(balance, 1)})
    out.reverse()  # newest first
    return out


def list_items(user: dict) -> dict:
    require_enabled()
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT * FROM inventory_items WHERE type='yarn' ORDER BY created_date DESC").fetchall()
        items = [_item_view(conn, r, _user_name(user)) for r in rows]
        conn.commit()
        return {"items": items}
    finally:
        _close(conn)


def item_detail(item_id: str, user: dict) -> dict:
    require_enabled()
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        item = _item_view(conn, _yarn_item(conn, item_id), _user_name(user))
        conn.commit()
        return {"item": item, "ledger": _ledger(conn, item_id)}
    finally:
        _close(conn)


# ---------------------------------------------------------------- changes
def _amount(body: dict, gpb: float | None, *, allow_zero: bool) -> tuple[float | None, float | None]:
    """(balls, grams) from a request: exactly one of them."""
    if not isinstance(body, dict):
        body = {}
    has_balls = body.get("balls") not in (None, "")
    has_grams = body.get("grams") not in (None, "")
    if has_balls == has_grams:
        raise StashError("Give either a number of balls or a number of grams.")
    if has_balls:
        balls = number(body["balls"], "The number of balls", high=MAX_BALLS, allow_zero=allow_zero)
        if not gpb and balls != int(balls):
            raise StashError("This yarn is counted in whole balls. Add its ball weight to count part balls.")
        return balls, None
    if not gpb:
        raise StashError("This yarn has no ball weight yet. Add the grams per ball first, then you can use grams.")
    return None, number(body["grams"], "The number of grams", high=MAX_GRAMS, allow_zero=allow_zero)


def _note(body: dict) -> str:
    note = str((body or {}).get("note") or "").strip()
    if len(note) > 300:
        raise StashError("The note is too long: keep it under 300 letters.")
    return note


def _change(item_id: str, body: dict, user: dict, kind: str) -> dict:
    require_enabled()
    created_by = _user_name(user)
    note = _note(body)
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        item = _yarn_item(conn, item_id)
        gpb = _gpb(_spec_row(conn, item["yarn_id"]))
        balls, grams = _amount(body, gpb, allow_zero=(kind == "correct"))
        old_qty = int(item["quantity"])
        with fork_hooks.stash_writing():
            if gpb:
                _reconcile(conn, item, gpb, old_qty, created_by)
                total, _ = _stock(conn, item_id)
                amount = grams if grams is not None else balls * gpb
                if kind == "purchase":
                    said = f"Bought {_balls_text(balls)}" if balls is not None else f"Bought {amount:g} g"
                    _append(conn, item_id, amount, "purchase", f"{said}. {note}".strip() if note else said, created_by)
                else:
                    said = (f"Counted {_balls_text(balls)}" if balls is not None else f"Weighed {amount:g} g")
                    _append(conn, item_id, amount - total, "correction", f"{said}. {note}".strip() if note else said,
                            created_by)
                new_qty = _sync_quantity(conn, item_id, gpb)
            else:
                new_qty = old_qty + int(balls) if kind == "purchase" else int(balls)
                conn.execute("UPDATE inventory_items SET quantity=? WHERE id=?", (new_qty, item_id))
            upstream_note = ("Bought more (stash)" if kind == "purchase" else "Corrected (stash)") + (f": {note}" if note else "")
            _upstream_log(conn, item_id, new_qty - old_qty, "added" if kind == "purchase" else "manual", upstream_note)
        conn.commit()
    finally:
        _close(conn)
    return item_detail(item_id, user)


def purchase(item_id: str, body: dict, user: dict) -> dict:
    return _change(item_id, body, user, "purchase")


def correct(item_id: str, body: dict, user: dict) -> dict:
    return _change(item_id, body, user, "correct")
