"""The /api/guided endpoints, end to end, with a pretend model. Fork-only (FORK.md).

Needs KNITTING_DATA_DIR, KNITTING_LOG_DIR and KNITTING_STATIC_DIR set to temporary folders, as the other API tests do.
"""
import json
import time
import unittest

from fastapi.testclient import TestClient

from tests.test_guide_builder_pipeline import LINES, FakeClient, tiny_pdf


class GuidedApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main
        from app.core.foundation import get_db
        from app.guided import jobs

        cls.jobs = jobs
        cls.get_db = staticmethod(get_db)
        cls.client = TestClient(main.app)
        cls.client.__enter__()
        status = cls.client.get("/api/setup/status").json()
        if status.get("setup_required"):
            tok = cls.client.post("/api/setup/admin", json={"username": "guidetest", "password": "guided-test-password-1"}).json()["token"]
        else:  # another test created the admin already
            tok = cls.client.post("/api/auth/login", json={"username": "guidetest", "password": "guided-test-password-1"}).json().get("token")
        cls.h = {"X-Session-Token": tok}
        cls._orig_client = jobs.ai.Client
        jobs.ai.Client = lambda cfg: FakeClient()

    @classmethod
    def tearDownClass(cls):
        cls.jobs.ai.Client = cls._orig_client
        cls.client.__exit__(None, None, None)

    def _set_ai(self, configured: bool):
        conn = self.get_db()
        for k, v in (("ai_base_url", "https://example.invalid/v1" if configured else ""), ("ai_api_key", "test-key" if configured else "")):
            conn.execute("INSERT INTO app_settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        conn.commit()
        conn.close()

    def _recipe(self, title: str) -> str:
        r = self.client.post("/api/recipes", data={"title": title, "description": "", "categories": "", "tags": ""},
                             files={"files": ("hat.pdf", tiny_pdf(LINES), "application/pdf")}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def _wait(self, rid: str, timeout: float = 30) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            d = self.client.get(f"/api/guided/recipes/{rid}", headers=self.h).json()
            if d["job"] and d["job"]["status"] in ("done", "failed", "cancelled"):
                return d
            time.sleep(0.2)
        self.fail("build did not finish")

    def test_switched_off_by_default_and_needs_ai(self):
        self.client.put("/api/guided/settings", json={"enabled": False}, headers=self.h)
        rid = self._recipe("Off switch hat")
        self.assertFalse(self.client.get("/api/guided/status", headers=self.h).json()["enabled"])
        self.assertEqual(self.client.post(f"/api/guided/recipes/{rid}/build", headers=self.h).status_code, 403)
        self.client.put("/api/guided/settings", json={"enabled": True}, headers=self.h)
        self._set_ai(False)
        r = self.client.post(f"/api/guided/recipes/{rid}/build", headers=self.h)
        self.assertEqual(r.status_code, 400)
        self.assertIn("AI connection", r.json()["detail"])

    def test_build_stores_guide_and_progress(self):
        self.client.put("/api/guided/settings", json={"enabled": True}, headers=self.h)
        self._set_ai(True)
        rid = self._recipe("Pretend hat")
        start = self.client.post(f"/api/guided/recipes/{rid}/build", headers=self.h)
        self.assertEqual(start.status_code, 200, start.text)
        d = self._wait(rid)
        self.assertEqual(d["job"]["status"], "done", d["job"]["error"])
        self.assertEqual(d["job"]["last_event"]["stage"], "done")
        stages = [e["stage"] for e in d["job"]["events"]]
        self.assertIn("sections", stages)
        guide = d["guide"]["guide"]
        self.assertEqual([s["name"] for s in guide["sections"]], ["Brim", "Crown"])
        self.assertEqual(d["guide"]["version"], 1)
        self.assertEqual(d["guide"]["review_state"], "unchecked")

    def test_only_one_build_at_a_time_and_cancel(self):
        self.client.put("/api/guided/settings", json={"enabled": True}, headers=self.h)
        self._set_ai(True)
        rid = self._recipe("Busy hat")
        conn = self.get_db()
        conn.execute("INSERT INTO guide_jobs (id, recipe_id, status, created_at) VALUES ('busyjob', ?, 'queued', '2026-01-01T00:00:00+00:00')", (rid,))
        conn.commit()
        conn.close()
        self.assertEqual(self.client.post(f"/api/guided/recipes/{rid}/build", headers=self.h).status_code, 409)
        r = self.client.post("/api/guided/jobs/busyjob/cancel", headers=self.h).json()
        self.assertEqual(r["job"]["status"], "cancelled")

    def test_settings_need_admin_and_a_model_name(self):
        r = self.client.put("/api/guided/settings", json={"model": ""}, headers=self.h)
        self.assertEqual(r.status_code, 400)
        import main
        with TestClient(main.app) as anonymous:  # no session cookie
            self.assertEqual(anonymous.get("/api/guided/settings").status_code, 401)


if __name__ == "__main__":
    unittest.main()
