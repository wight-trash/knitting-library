"""Upstream bugs fixed in the fork (FORK.md, "Upstream bug fixed in the fork"), end to end through the API.

* Import wizard drafts that are not confirmed yet ('staged') stayed in the library list.
* Deleting a project session, clearing a pattern's session history, or deleting a pattern failed (500) once a
  session had taken balls from the inventory, because inventory_log points at the session and the recipe.
  The failure also left the database locked for every other request.
* Deleting a pattern left its guided version behind, ready to show on a new pattern with the same title.

Needs KNITTING_DATA_DIR, KNITTING_LOG_DIR and KNITTING_STATIC_DIR set to temporary folders, as the other API tests do.
"""
import io
import unittest
import uuid

from fastapi.testclient import TestClient
from PIL import Image


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (90, 140, 70)).save(out, "PNG")
    return out.getvalue()


class UpstreamFixesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main
        from app.core.foundation import get_db

        cls.get_db = staticmethod(get_db)
        cls.client = TestClient(main.app)
        cls.client.__enter__()
        status = cls.client.get("/api/setup/status").json()
        if status.get("setup_required"):
            tok = cls.client.post("/api/setup/admin", json={"username": "guidetest", "password": "guided-test-password-1"}).json()["token"]
        else:  # another test created the admin already
            tok = cls.client.post("/api/auth/login", json={"username": "guidetest", "password": "guided-test-password-1"}).json().get("token")
        cls.h = {"X-Session-Token": tok}

    @classmethod
    def tearDownClass(cls):
        cls.client.put("/api/fork/settings", json={"stash_enabled": False}, headers=cls.h)
        cls.client.__exit__(None, None, None)

    # ------------------------------------------------------------ helpers
    def _sql(self, sql: str, params=()):
        conn = self.get_db()
        try:
            rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
            conn.commit()
            return rows
        finally:
            conn.close()

    def _library_ids(self, search: str, headers=None) -> list[str]:
        r = self.client.get("/api/recipes", params={"search": search, "per_page": 200}, headers=headers or self.h)
        self.assertEqual(r.status_code, 200, r.text)
        return [x["id"] for x in r.json()["recipes"]]

    def _recipe(self, title: str) -> str:
        r = self.client.post("/api/recipes", data={"title": title}, files={"files": ("p.png", _png(), "image/png")},
                             headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def _stock(self, qty: int = 6, grams_per_ball=None) -> str:
        r = self.client.post("/api/yarns", data={"name": f"Pretend Wren Wool {uuid.uuid4().hex[:6]}"}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        yarn_id = r.json()["id"]
        if grams_per_ball:
            r = self.client.put(f"/api/stash/yarns/{yarn_id}/spec", json={"grams_per_ball": grams_per_ball}, headers=self.h)
            self.assertEqual(r.status_code, 200, r.text)
        r = self.client.post("/api/inventory", json={"type": "yarn", "yarn_id": yarn_id, "name": "Hall cupboard",
                                                     "quantity": qty}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def _start(self, rid: str, item_id: str, balls: int = 2, headers=None) -> str:
        r = self.client.post(f"/api/recipes/{rid}/start", json={"inventory_item_id": item_id, "skeins_used": balls},
                             headers=headers or self.h)
        self.assertEqual(r.status_code, 200, r.text)
        sid = r.json()["active_session_id"]
        self.assertTrue(sid)
        return sid

    def _log(self, item_id: str) -> list[dict]:
        return self._sql("SELECT * FROM inventory_log WHERE item_id=? AND reason='project_start'", (item_id,))

    def _quantity(self, item_id: str) -> int:
        return self._sql("SELECT quantity FROM inventory_items WHERE id=?", (item_id,))[0]["quantity"]

    def _still_answers(self):
        r = self.client.get("/api/setup/status")  # failed deletes used to leave the database locked
        self.assertEqual(r.status_code, 200, r.text)

    # ------------------------------------------------------------ staged imports
    def test_staged_import_is_not_in_the_library_until_confirmed(self):
        name = f"Staged Puffin Socks {uuid.uuid4().hex[:6]}"
        r = self.client.post("/api/import/upload-group", data={"group_name": name},
                             files=[("files", ("one.png", _png(), "image/png"))], headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        staged = r.json()["recipe_id"]

        self.assertNotIn(staged, self._library_ids(name))
        r = self.client.get("/api/recipes", params={"per_page": 200, "sort": "created_desc"}, headers=self.h)
        self.assertNotIn(staged, [x["id"] for x in r.json()["recipes"]])
        queue = self.client.get("/api/import/queue", headers=self.h).json()
        self.assertIn(staged, [i["recipe_id"] for i in queue["items"]])  # the wizard can still resume it

        r = self.client.post(f"/api/import/confirm/{staged}", json={"title": name}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn(r.json()["recipe_id"], self._library_ids(name))

    def test_discarded_import_never_shows(self):
        name = f"Skipped Puffin Hat {uuid.uuid4().hex[:6]}"
        staged = self.client.post("/api/import/upload-group", data={"group_name": name},
                                  files=[("files", ("one.png", _png(), "image/png"))], headers=self.h).json()["recipe_id"]
        self.assertEqual(self.client.post(f"/api/import/discard/{staged}", headers=self.h).status_code, 200)
        self.assertEqual(self._library_ids(name), [])

    # ------------------------------------------------------------ sessions that used stock
    def test_delete_session_that_used_stock(self):
        self.client.put("/api/fork/settings", json={"stash_enabled": True}, headers=self.h)  # the stash ledger too
        try:
            item = self._stock(6, grams_per_ball=50)
            rid = self._recipe(f"Wren Hat {uuid.uuid4().hex[:6]}")
            sid = self._start(rid, item)
            self.assertEqual(self._log(item)[0]["session_id"], sid)
            ledger_sql = "SELECT * FROM stash_ledger WHERE item_id=? AND project_session_id=?"
            self.assertEqual(len(self._sql(ledger_sql, (item, sid))), 1)

            r = self.client.delete(f"/api/recipes/{rid}/sessions/{sid}", headers=self.h)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["sessions"], [])
            log = self._log(item)
            self.assertEqual(len(log), 1)  # the stock history keeps the balls that were used
            self.assertIsNone(log[0]["session_id"])
            self.assertEqual(log[0]["recipe_id"], rid)
            self.assertEqual(log[0]["change"], -2)
            self.assertEqual(self._quantity(item), 4)
            self.assertEqual(len(self._sql(ledger_sql, (item, sid))), 1)  # no foreign key: the gram history stays
            self.assertEqual(self.client.get(f"/api/stash/items/{item}", headers=self.h).status_code, 200)
            self._still_answers()
        finally:
            self.client.put("/api/fork/settings", json={"stash_enabled": False}, headers=self.h)

    def test_clear_session_history_that_used_stock(self):
        item = self._stock(6)
        rid = self._recipe(f"Wren Mitts {uuid.uuid4().hex[:6]}")
        self._start(rid, item)
        self.assertEqual(self.client.post(f"/api/recipes/{rid}/finish", json={}, headers=self.h).status_code, 200)
        self._start(rid, item)

        r = self.client.delete(f"/api/recipes/{rid}/sessions", headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["sessions"], [])
        log = self._log(item)
        self.assertEqual(len(log), 2)
        self.assertTrue(all(row["session_id"] is None for row in log))
        self.assertEqual(self._quantity(item), 2)
        self._still_answers()

    def test_clear_session_history_as_a_knitter_leaves_other_sessions_linked(self):
        name = f"fixknitter{uuid.uuid4().hex[:6]}"
        r = self.client.post("/api/admin/users", json={"username": name, "password": "knitter-pass-123"}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        kh = {"X-Session-Token": self.client.post("/api/auth/login", json={"username": name, "password": "knitter-pass-123"}).json()["token"]}
        item = self._stock(6)
        rid = self._recipe(f"Wren Scarf {uuid.uuid4().hex[:6]}")
        admin_sid = self._start(rid, item)
        knitter_sid = self._start(rid, item, headers=kh)

        r = self.client.delete(f"/api/recipes/{rid}/sessions", headers=kh)
        self.assertEqual(r.status_code, 200, r.text)
        links = {row["session_id"] for row in self._log(item)}
        self.assertEqual(links, {admin_sid, None})
        self.assertNotIn(knitter_sid, links)
        self._still_answers()

    def test_delete_recipe_that_used_stock_and_had_a_guide(self):
        item = self._stock(6)
        rid = self._recipe(f"Wren Cardigan {uuid.uuid4().hex[:6]}")
        self._start(rid, item)
        from app.fork_migrations import ensure_fork_schema
        ensure_fork_schema()
        self._sql("INSERT INTO guides (recipe_id, guide, built_at, updated_at) VALUES (?, '{}', 'x', 'x')", (rid,))
        self._sql("INSERT INTO guide_jobs (id, recipe_id, status, created_at) VALUES (?, ?, 'done', 'x')", (uuid.uuid4().hex, rid))

        r = self.client.delete(f"/api/recipes/{rid}", headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        log = self._log(item)
        self.assertEqual(len(log), 1)
        self.assertIsNone(log[0]["recipe_id"])
        self.assertIsNone(log[0]["session_id"])
        self.assertIn("Wren Cardigan", log[0]["note"])  # the history still names the pattern
        self.assertEqual(self._sql("SELECT * FROM guides WHERE recipe_id=?", (rid,)), [])
        self.assertEqual(self._sql("SELECT * FROM guide_jobs WHERE recipe_id=?", (rid,)), [])
        self._still_answers()


if __name__ == "__main__":
    unittest.main()


class YarnDeleteTests(unittest.TestCase):
    """Deleting a yarn or colour that is in the stash used to fail and lock the database; now it is refused."""

    def test_in_stock_yarn_and_colour_are_refused_and_the_app_keeps_working(self):
        import main
        from fastapi.testclient import TestClient
        c = TestClient(main.app, raise_server_exceptions=False)
        status = c.get("/api/setup/status").json()
        if status.get("setup_required"):
            tok = c.post("/api/setup/admin", json={"username": "guidetest", "password": "guided-test-password-1"}).json()["token"]
        else:
            tok = c.post("/api/auth/login", json={"username": "guidetest", "password": "guided-test-password-1"}).json().get("token")
        if not tok:
            self.skipTest("another test created a different admin")
        h = {"X-Session-Token": tok}
        y = c.post("/api/yarns", data={"name": "Made-up Wool"}, headers=h).json()
        col = c.post(f"/api/yarns/{y['id']}/colours", json={"name": "Made-up Red"}, headers=h).json()
        c.post("/api/inventory", json={"type": "yarn", "yarn_id": y["id"], "yarn_colour_id": col["id"],
                                       "name": "Made-up Wool", "quantity": 2}, headers=h)
        r = c.delete(f"/api/yarns/{y['id']}/colours/{col['id']}", headers=h)
        self.assertEqual(r.status_code, 409)
        self.assertIn("stash", r.json()["detail"])
        self.assertEqual(c.get("/api/yarns", headers=h).status_code, 200)
        r = c.delete(f"/api/yarns/{y['id']}", headers=h)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(c.get("/api/inventory", headers=h).status_code, 200)
        unused = c.post("/api/yarns", data={"name": "Unused Wool"}, headers=h).json()
        self.assertEqual(c.delete(f"/api/yarns/{unused['id']}", headers=h).status_code, 200)
