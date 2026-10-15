"""The stash in grams (/api/stash, the upstream hook, the ball-band reader and the picture fetch). Fork-only (FORK.md).

Needs KNITTING_DATA_DIR, KNITTING_LOG_DIR and KNITTING_STATIC_DIR set to temporary folders, as the other API tests do.
Every yarn, brand and address here is made up; nothing reaches the internet or a real AI service.
"""
import io
import json
import socket
import unittest
import uuid
from unittest import mock

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from tests.test_guide_builder_pipeline import LINES, tiny_pdf


def _picture(fmt: str = "PNG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (180, 90, 120)).save(out, fmt)
    return out.getvalue()


class StashApiTests(unittest.TestCase):
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

    def setUp(self):
        self._switch(True)

    # ------------------------------------------------------------ helpers
    def _switch(self, on: bool):
        r = self.client.put("/api/fork/settings", json={"stash_enabled": on}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["stash_enabled"], on)

    def _sql(self, sql: str, params=()):
        conn = self.get_db()
        try:
            rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
            conn.commit()
            return rows
        finally:
            conn.close()

    def _yarn(self, gpb=None) -> str:
        yarn_id = str(uuid.uuid4())
        self._sql("INSERT INTO yarns (id, name, created_date) VALUES (?, ?, '2026-10-15T00:00:00')",
                  (yarn_id, f"Pretend Puffin Yarn {yarn_id[:6]}"))
        if gpb is not None:
            r = self.client.put(f"/api/stash/yarns/{yarn_id}/spec", json={"grams_per_ball": gpb}, headers=self.h)
            self.assertEqual(r.status_code, 200, r.text)
        return yarn_id

    def _item(self, yarn_id, qty: int) -> str:
        r = self.client.post("/api/inventory", json={"type": "yarn", "yarn_id": yarn_id, "name": "Moss shelf",
                                                     "quantity": qty}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def _ledger(self, item_id):
        return self._sql("SELECT * FROM stash_ledger WHERE item_id=? ORDER BY created_at, rowid", (item_id,))

    def _qty(self, item_id) -> int:
        return self.client.get(f"/api/inventory/{item_id}", headers=self.h).json()["quantity"]

    def _view(self, item_id) -> dict:
        r = self.client.get(f"/api/stash/items/{item_id}", headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _adjust(self, item_id, change):
        r = self.client.post(f"/api/inventory/{item_id}/adjust", json={"change": change, "reason": "manual"}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    # ------------------------------------------------------------ the switch
    def test_switch_off_means_no_ledger_writes_and_403(self):
        yarn = self._yarn(gpb=50)
        self._switch(False)
        item = self._item(yarn, 3)
        self._adjust(item, 1)
        self._adjust(item, -2)
        self.assertEqual(self._ledger(item), [])
        self.assertEqual(self._qty(item), 2)
        st = self.client.get("/api/stash/status", headers=self.h)
        self.assertEqual(st.status_code, 200)
        self.assertFalse(st.json()["enabled"])
        self.assertFalse(st.json()["ballband_available"])
        for method, path in (("get", "/api/stash/items"), ("get", f"/api/stash/items/{item}"),
                             ("post", f"/api/stash/items/{item}/purchase"), ("post", f"/api/stash/items/{item}/correct"),
                             ("get", f"/api/stash/yarns/{yarn}/spec"), ("get", "/api/stash/image?url=http://127.0.0.1/a.png")):
            kw = {"json": {"balls": 1}} if method == "post" else {}
            r = getattr(self.client, method)(path, headers=self.h, **kw)
            self.assertEqual(r.status_code, 403, path)
            self.assertIn("switched off", r.json()["detail"])
        r = self.client.post("/api/stash/ballband", files={"image": ("band.png", _picture(), "image/png")}, headers=self.h)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self._ledger(item), [])
        # Back on: the first read opens the balance from the ball count kept meanwhile.
        self._switch(True)
        v = self._view(item)
        self.assertEqual(v["item"]["grams"], 100)
        self.assertEqual([e["reason"] for e in v["ledger"]], ["opening"])

    def test_fork_settings_and_guided_settings_agree(self):
        r = self.client.put("/api/fork/settings", json={"guides_enabled": True, "guide_model": "pretend/model-1"}, headers=self.h)
        self.assertEqual(r.json(), {"stash_enabled": True, "guides_enabled": True, "guide_model": "pretend/model-1"})
        g = self.client.get("/api/guided/settings", headers=self.h).json()
        self.assertEqual(g, {"enabled": True, "model": "pretend/model-1"})
        self.client.put("/api/guided/settings", json={"enabled": False, "model": "anthropic/claude-haiku-5.5"}, headers=self.h)
        r = self.client.get("/api/fork/settings", headers=self.h).json()
        self.assertEqual(r, {"stash_enabled": True, "guides_enabled": False, "guide_model": "anthropic/claude-haiku-5.5"})
        self.assertEqual(self.client.put("/api/fork/settings", json={"guide_model": ""}, headers=self.h).status_code, 400)
        import main
        with TestClient(main.app) as anonymous:
            self.assertEqual(anonymous.get("/api/fork/settings").status_code, 401)

    # ------------------------------------------------------------ ledger rules
    def test_opening_balance_written_once(self):
        yarn = self._yarn()
        item = self._item(yarn, 4)
        self.assertEqual(self._ledger(item), [])            # no ball weight yet: whole balls only
        self.client.put(f"/api/stash/yarns/{yarn}/spec", json={"grams_per_ball": 50}, headers=self.h)
        v = self._view(item)
        self.assertEqual((v["item"]["mode"], v["item"]["grams"], v["item"]["balls"], v["item"]["quantity"]),
                         ("grams", 200, 4.0, 4))
        self.client.get(f"/api/stash/items/{item}", headers=self.h)
        self.client.get("/api/stash/items", headers=self.h)
        rows = self._ledger(item)
        self.assertEqual([(r["reason"], r["change_g"]) for r in rows], [("opening", 200)])
        self.assertEqual(rows[0]["created_by"], "guidetest")

    def test_purchase_in_balls_and_grams(self):
        item = self._item(self._yarn(gpb=50), 2)
        r = self.client.post(f"/api/stash/items/{item}/purchase", json={"balls": 1.5, "note": "Wool fair"}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        it = r.json()["item"]
        self.assertEqual((it["grams"], it["balls"], it["quantity"]), (175, 3.5, 3))
        r = self.client.post(f"/api/stash/items/{item}/purchase", json={"grams": "30"}, headers=self.h)
        it = r.json()["item"]
        self.assertEqual((it["grams"], it["balls"], it["quantity"]), (205, 4.1, 4))
        self.assertEqual(self._qty(item), 4)
        ledger = r.json()["ledger"]
        self.assertEqual([e["reason"] for e in ledger], ["purchase", "purchase", "ball_count"])  # newest first
        self.assertEqual([e["balance_g"] for e in ledger], [205, 175, 100])
        self.assertIn("Wool fair", ledger[1]["note"])
        log = self._sql("SELECT change, reason FROM inventory_log WHERE item_id=? ORDER BY created_at", (item,))
        self.assertEqual(log, [{"change": 2, "reason": "added"}, {"change": 1, "reason": "added"}, {"change": 1, "reason": "added"}])
        for bad in ({}, {"balls": 1, "grams": 50}, {"balls": -1}, {"grams": 0}, {"balls": "lots"}):
            r = self.client.post(f"/api/stash/items/{item}/purchase", json=bad, headers=self.h)
            self.assertEqual(r.status_code, 400, bad)
        self.assertEqual(self.client.post("/api/stash/items/nope/purchase", json={"balls": 1}, headers=self.h).status_code, 404)

    def test_correction_writes_the_difference(self):
        item = self._item(self._yarn(gpb=50), 4)
        r = self.client.post(f"/api/stash/items/{item}/correct", json={"grams": 215}, headers=self.h)
        it = r.json()["item"]
        self.assertEqual((it["grams"], it["balls"], it["quantity"]), (215, 4.3, 4))
        r = self.client.post(f"/api/stash/items/{item}/correct", json={"balls": 2}, headers=self.h)
        self.assertEqual(r.json()["item"]["grams"], 100)
        r = self.client.post(f"/api/stash/items/{item}/correct", json={"grams": 0}, headers=self.h)
        self.assertEqual((r.json()["item"]["grams"], r.json()["item"]["quantity"]), (0, 0))
        rows = self._ledger(item)
        self.assertEqual([(x["reason"], x["change_g"]) for x in rows],
                         [("ball_count", 200), ("correction", 15), ("correction", -115), ("correction", -100)])
        self.assertEqual(self.client.post(f"/api/stash/items/{item}/correct", json={"grams": -5}, headers=self.h).status_code, 400)

    def test_quantity_is_whole_balls_rounded_down(self):
        item = self._item(self._yarn(gpb=50), 0)
        r = self.client.post(f"/api/stash/items/{item}/purchase", json={"grams": 149}, headers=self.h)
        it = r.json()["item"]
        self.assertEqual((it["quantity"], it["balls"]), (2, 2.9))   # 2.98 balls: never shown as 3.0
        self.assertEqual(self._qty(item), 2)

    def test_ball_weight_change_keeps_the_ball_count(self):
        yarn = self._yarn(gpb=50)
        item = self._item(yarn, 4)
        self.client.post(f"/api/stash/items/{item}/correct", json={"grams": 215}, headers=self.h)
        r = self.client.put(f"/api/stash/yarns/{yarn}/spec", json={"grams_per_ball": 100, "weight": "DK"}, headers=self.h)
        self.assertEqual(r.json()["spec"]["grams_per_ball"], 100)
        it = self._view(item)["item"]
        self.assertEqual((it["grams"], it["balls"], it["quantity"]), (430, 4.3, 4))
        self.assertEqual(it["spec"]["weight"], "DK")

    def test_spec_validation(self):
        yarn = self._yarn()
        for bad in ({"grams_per_ball": "heavy"}, {"grams_per_ball": 0}, {"weight_category": 9},
                    {"weight_category": 2.5}, {"source": "rumour"}, {"care": "x" * 600}):
            r = self.client.put(f"/api/stash/yarns/{yarn}/spec", json=bad, headers=self.h)
            self.assertEqual(r.status_code, 400, bad)
        r = self.client.put(f"/api/stash/yarns/{yarn}/spec",
                            json={"grams_per_ball": "50", "metres_per_ball": "4,5", "needle_mm_min": 4.5, "needle_mm_max": 3.5,
                                  "weight_category": 3, "fibre": "Pretend wool"}, headers=self.h)
        spec = r.json()["spec"]
        self.assertEqual((spec["grams_per_ball"], spec["metres_per_ball"], spec["needle_mm_min"], spec["needle_mm_max"]),
                         (50, 4.5, 3.5, 4.5))
        self.assertEqual(spec["source"], "manual")
        self.assertEqual(self.client.get(f"/api/stash/yarns/{yarn}/spec", headers=self.h).json()["spec"]["fibre"], "Pretend wool")
        self.assertEqual(self.client.get("/api/stash/yarns/missing/spec", headers=self.h).status_code, 404)

    # ------------------------------------------------------------ the hook
    def test_hook_follows_plus_and_minus_buttons(self):
        item = self._item(self._yarn(gpb=50), 4)
        self.client.post(f"/api/stash/items/{item}/correct", json={"grams": 215}, headers=self.h)
        self.assertEqual(self._adjust(item, 1)["quantity"], 5)
        self.assertEqual(self._view(item)["item"]["grams"], 265)
        self._adjust(item, -1)
        self._adjust(item, -1)
        it = self._view(item)["item"]
        self.assertEqual((it["grams"], it["balls"], it["quantity"]), (165, 3.3, 3))
        notes = [e["note"] for e in self._view(item)["ledger"][:3]]
        self.assertTrue(all("ball count buttons" in n for n in notes), notes)

    def test_hook_follows_upstream_edits_and_catches_up(self):
        from app import fork_hooks
        item = self._item(self._yarn(gpb=50), 4)
        self._view(item)
        # Upstream's edit form never changes the quantity: nothing moves.
        r = self.client.put(f"/api/inventory/{item}", json={"name": "Moss shelf (top)", "quantity": 9}, headers=self.h)
        self.assertEqual(r.json()["quantity"], 4)
        self.assertEqual(len(self._ledger(item)), 1)
        # An upstream quantity edit through the hook, in the caller's transaction.
        conn = self.get_db()
        conn.execute("UPDATE inventory_items SET quantity=7 WHERE id=?", (item,))
        fork_hooks.after_quantity_change(conn, item, 4, None, "edit", "pretend-user")
        conn.commit()
        conn.close()
        rows = self._ledger(item)
        self.assertEqual((rows[-1]["reason"], rows[-1]["change_g"], rows[-1]["created_by"]), ("ball_count", 150, "pretend-user"))
        self.assertEqual(self._view(item)["item"]["grams"], 350)
        # Changed behind the stash's back (no hook): the next read brings the grams in line with the count.
        self._sql("UPDATE inventory_items SET quantity=2 WHERE id=?", (item,))
        it = self._view(item)["item"]
        self.assertEqual((it["grams"], it["quantity"]), (100, 2))
        self.assertEqual(self._ledger(item)[-1]["reason"], "ball_count")

    def test_hook_follows_project_start(self):
        item = self._item(self._yarn(gpb=50), 5)
        r = self.client.post("/api/recipes", data={"title": "Pretend stash hat", "description": "", "categories": "", "tags": ""},
                             files={"files": ("hat.pdf", tiny_pdf(LINES), "application/pdf")}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        rid = r.json()["id"]
        r = self.client.post(f"/api/recipes/{rid}/start", json={"inventory_item_id": item, "skeins_used": 2}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self._qty(item), 3)
        rows = self._ledger(item)
        self.assertEqual((rows[-1]["reason"], rows[-1]["change_g"]), ("ball_count", -100))
        self.assertTrue(rows[-1]["project_session_id"])
        self.assertEqual(self._view(item)["item"]["grams"], 150)

    def test_no_double_counting_from_the_stash_itself(self):
        from app import fork_hooks
        item = self._item(self._yarn(gpb=50), 2)
        self.client.post(f"/api/stash/items/{item}/purchase", json={"balls": 2}, headers=self.h)
        self.assertEqual([r["reason"] for r in self._ledger(item)], ["ball_count", "purchase"])
        self.assertEqual(self._view(item)["item"]["grams"], 200)
        conn = self.get_db()
        with fork_hooks.stash_writing():
            fork_hooks.after_quantity_change(conn, item, 4, 9, "adjust", "x")
        conn.commit()
        conn.close()
        self.assertEqual(len(self._ledger(item)), 2)

    def test_hook_failure_never_breaks_upstream(self):
        from app.stash import ledger
        item = self._item(self._yarn(gpb=50), 2)
        before = self._ledger(item)
        with mock.patch.object(ledger, "_sync_quantity", side_effect=RuntimeError("pretend failure")), \
                self.assertLogs("knitting.fork.stash", level="ERROR"):
            self.assertEqual(self._adjust(item, 1)["quantity"], 3)
        self.assertEqual(self._ledger(item), before)          # rolled back to the savepoint, nothing half-written
        it = self._view(item)["item"]                          # and the next read catches up
        self.assertEqual((it["grams"], it["quantity"]), (150, 3))

    def test_items_without_ball_weight_stay_in_whole_balls(self):
        item = self._item(self._yarn(), 3)
        it = self._view(item)["item"]
        self.assertEqual((it["mode"], it["grams"], it["balls"], it["quantity"]), ("balls", None, None, 3))
        r = self.client.post(f"/api/stash/items/{item}/purchase", json={"balls": 2}, headers=self.h)
        self.assertEqual(r.json()["item"]["quantity"], 5)
        self.assertEqual(self.client.post(f"/api/stash/items/{item}/purchase", json={"grams": 50}, headers=self.h).status_code, 400)
        self.assertEqual(self.client.post(f"/api/stash/items/{item}/purchase", json={"balls": 1.5}, headers=self.h).status_code, 400)
        r = self.client.post(f"/api/stash/items/{item}/correct", json={"balls": 1}, headers=self.h)
        self.assertEqual(r.json()["item"]["quantity"], 1)
        self._adjust(item, 1)
        self.assertEqual(self._ledger(item), [])
        listed = {i["id"]: i for i in self.client.get("/api/stash/items", headers=self.h).json()["items"]}
        self.assertEqual(listed[item]["mode"], "balls")
        tool = self.client.post("/api/inventory", json={"type": "tool", "name": "Pretend needles", "quantity": 1}, headers=self.h).json()
        self.assertNotIn(tool["id"], listed)
        self.assertEqual(self.client.get(f"/api/stash/items/{tool['id']}", headers=self.h).status_code, 404)

    # ------------------------------------------------------------ picture fetch
    def test_image_fetch_refuses_private_addresses(self):
        from app.stash import imagefetch

        def never(request):
            raise AssertionError("no request should be made")

        with mock.patch.object(imagefetch, "TRANSPORT", httpx.MockTransport(never)):
            for url in ("http://127.0.0.1/ball.png", "http://10.0.0.5/ball.png", "http://localhost/ball.png",
                        "http://[::1]/ball.png", "ftp://shop.example/ball.png", "", "not a link"):
                r = self.client.get("/api/stash/image", params={"url": url}, headers=self.h)
                self.assertEqual(r.status_code, 400, url)
                self.assertIn("cannot be used", r.json()["detail"])

    def test_image_fetch_public_picture_with_pretend_web(self):
        from app.stash import imagefetch
        png = _picture()
        real_getaddrinfo = socket.getaddrinfo

        def fake_getaddrinfo(host, port, *a, **kw):
            if host == "shop.example":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("151.101.2.3", port or 80))]
            return real_getaddrinfo(host, port, *a, **kw)

        def web(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/ball.png":
                return httpx.Response(200, content=png, headers={"content-type": "image/png"})
            if path == "/moved":
                return httpx.Response(302, headers={"location": "/ball.png"})
            if path == "/sneaky":
                return httpx.Response(302, headers={"location": "http://10.1.2.3/ball.png"})
            if path == "/page":
                return httpx.Response(200, content=b"<html>pretend shop</html>", headers={"content-type": "text/html"})
            if path == "/svg":
                return httpx.Response(200, content=b"<svg></svg>", headers={"content-type": "image/svg+xml"})
            if path == "/liar.png":
                return httpx.Response(200, content=b"<html>not a picture</html>", headers={"content-type": "image/png"})
            if path == "/huge.png":
                return httpx.Response(200, content=png + b"\0" * 2048, headers={"content-type": "image/png"})
            return httpx.Response(404)

        with mock.patch("socket.getaddrinfo", fake_getaddrinfo), \
                mock.patch.object(imagefetch, "TRANSPORT", httpx.MockTransport(web)), \
                mock.patch.object(imagefetch, "MAX_BYTES", len(png) + 1024):
            def get(path):
                return self.client.get("/api/stash/image", params={"url": f"https://shop.example{path}"}, headers=self.h)

            for path in ("/ball.png", "/moved"):
                r = get(path)
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(r.headers["content-type"], "image/png")
                self.assertEqual(r.content, png)
                self.assertEqual(r.headers["x-content-type-options"], "nosniff")
            self.assertEqual(get("/sneaky").status_code, 400)
            for path in ("/page", "/svg", "/liar.png"):
                self.assertEqual(get(path).status_code, 415, path)
            self.assertEqual(get("/huge.png").status_code, 413)
            self.assertEqual(get("/gone.png").status_code, 502)

    # ------------------------------------------------------------ ball band
    def _set_ai(self, configured: bool):
        for k, v in (("ai_base_url", "https://example.invalid/v1" if configured else ""), ("ai_api_key", "test-key" if configured else "")):
            self._sql("INSERT INTO app_settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))

    def test_ballband_reader_with_pretend_model(self):
        from app.guide_builder import ai
        answer = {
            "name": {"text": "Cloudberry Twist", "confidence": "high"},
            "brand": {"text": "Puddle & Fern", "confidence": "high"},
            "colour_name": {"text": "Harbour Fog", "confidence": "high"},
            "colour_number": {"text": "0417", "confidence": "medium"},
            "dye_lot": {"text": "B22", "confidence": "low"},
            "fibre": {"text": "70% merino, 30% pretend silk", "confidence": "high"},
            "weight": {"text": "DK", "confidence": "high"},
            "care": {"text": "Hand wash cool", "confidence": "medium"},
            "weight_symbol": {"value": None, "confidence": "low"},
            "ball_weight": {"text": "1.75 oz", "value": 1.75, "unit": "oz", "confidence": "high"},
            "length": {"text": "137 yds", "value": 137, "unit": "yds", "confidence": "high"},
            "needle": {"text": "US 6", "confidence": "low"},
            "gauge": {"text": "22 sts x 30 rows = 4 in", "stitches": 22, "rows": 30, "over_value": 4, "over_unit": "in",
                      "confidence": "high"},
        }
        calls = []

        class FakeBandClient:
            def __init__(self, cfg):
                self.cfg = cfg

            def json(self, system, content, schema, name, **kw):
                calls.append({"name": name, "kinds": [p["type"] for p in content], "schema": schema, "model": self.cfg.model})
                return ai.Answer(json.loads(json.dumps(answer)), "strict", {})

            def close(self):
                pass

        self._set_ai(False)
        self.assertFalse(self.client.get("/api/stash/status", headers=self.h).json()["ballband_available"])
        r = self.client.post("/api/stash/ballband", files={"image": ("band.jpg", _picture("JPEG"), "image/jpeg")}, headers=self.h)
        self.assertEqual(r.status_code, 400)
        self.assertIn("AI connection", r.json()["detail"])
        self._set_ai(True)
        self.assertTrue(self.client.get("/api/stash/status", headers=self.h).json()["ballband_available"])
        with mock.patch.object(ai, "Client", FakeBandClient):
            r = self.client.post("/api/stash/ballband", files={"image": ("band.jpg", _picture("JPEG"), "image/jpeg")}, headers=self.h)
            self.assertEqual(r.status_code, 200, r.text)
            bad = self.client.post("/api/stash/ballband", files={"image": ("band.txt", b"just words", "text/plain")}, headers=self.h)
            self.assertEqual(bad.status_code, 415)
        self._set_ai(False)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["name"], "ball_band")
        self.assertEqual(calls[0]["kinds"], ["text", "image_url"])
        self.assertIn("ball_weight", calls[0]["schema"]["required"])
        d = r.json()
        f = d["fields"]
        self.assertEqual((f["grams_per_ball"]["value"], f["grams_per_ball"]["original_value"], f["grams_per_ball"]["original_unit"]),
                         (49.6, 1.75, "oz"))
        self.assertEqual((f["metres_per_ball"]["value"], f["metres_per_ball"]["text"]), (125.3, "137 yds"))
        self.assertEqual((f["needle"]["mm_min"], f["needle"]["mm_max"], f["needle"]["text"]), (4.0, 4.0, "US 6"))
        self.assertEqual((f["gauge"]["stitches_per_10cm"], f["gauge"]["rows_per_10cm"]), (21.7, 29.5))
        self.assertEqual(f["weight_category"]["value"], 3)
        self.assertEqual(f["colour_number"]["confidence"], "medium")
        self.assertIn("needle", d["low_confidence"])
        self.assertIn("dye_lot", d["low_confidence"])
        self.assertNotIn("weight_category", d["low_confidence"])
        spec = d["spec"]
        self.assertEqual((spec["grams_per_ball"], spec["metres_per_ball"], spec["gauge_stitches"], spec["gauge_over_cm"],
                          spec["source"]), (49.6, 125.3, 21.7, 10.0, "ball_band"))
        self.assertEqual(d["yarn_form"]["name"], "Puddle & Fern Cloudberry Twist")
        self.assertEqual(d["yarn_form"]["colour"], "Harbour Fog 0417")
        self.assertEqual(d["yarn_form"]["needles"], "4 mm")
        # The proposed spec saves as it is.
        yarn = self._yarn()
        r = self.client.put(f"/api/stash/yarns/{yarn}/spec", json=spec, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["spec"]["source"], "ball_band")

    def test_needle_and_weight_readings(self):
        from app.stash import ballband
        self.assertEqual(ballband.needle_range("3.5-4 mm"), (3.5, 4.0))
        self.assertEqual(ballband.needle_range("3,5 – 4,5 mm / US 4-7"), (3.5, 4.5))
        self.assertEqual(ballband.needle_range("US 6-7"), (4.0, 4.5))
        self.assertEqual(ballband.needle_range("US 8"), (5.0, 5.0))
        self.assertEqual(ballband.needle_range("UK 8"), (4.0, 4.0))
        self.assertEqual(ballband.needle_range(None), (None, None))
        self.assertEqual(ballband.weight_category("Aran", None), 4)
        self.assertEqual(ballband.weight_category("Super chunky", None), 6)
        self.assertEqual(ballband.weight_category("4-ply", None), 1)
        self.assertEqual(ballband.weight_category("DROPS group B", None), None)
        self.assertEqual(ballband.weight_category("whatever", 5), 5)


if __name__ == "__main__":
    unittest.main()
