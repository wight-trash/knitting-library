"""AI tuning (FORK.md "AI tuning"): one model for every feature, a reasoning effort per feature that the model actually
offers, model facts from OpenRouter's list, admin-only technical failure reasons, and answers checked against their
schema before the guide builder uses them.

OpenRouter's model list is replaced by a copy of the real fields (fetched 15 November 2026), so nothing goes out.
Needs KNITTING_DATA_DIR, KNITTING_LOG_DIR and KNITTING_STATIC_DIR set to temporary folders, as the other API tests do.
"""
import asyncio
import copy
import json
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

CATALOGUE = {
    "anthropic/claude-haiku-5.5": {
        "id": "anthropic/claude-haiku-5.5", "name": "Anthropic: Claude Haiku 5.5", "context_length": 1000000,
        "architecture": {"input_modalities": ["text", "image"]},
        "pricing": {"prompt": "0.0000001", "completion": "0.0000005"},
        "supported_parameters": ["include_reasoning", "max_tokens", "reasoning", "reasoning_effort", "response_format",
                                 "structured_outputs"],
        "default_parameters": {},
        "reasoning": {"mandatory": False, "supported_efforts": ["max", "xhigh", "high", "medium", "low", "none"],
                      "default_effort": "medium"},
        "top_provider": {"context_length": 1000000, "max_completion_tokens": 128000},
    },
    "mistralai/mistral-large-4-0": {
        "id": "mistralai/mistral-large-4-0", "name": "Mistral Large 4", "context_length": 1048576,
        "architecture": {"input_modalities": ["text", "image"]},
        "pricing": {"prompt": "0.0000007", "completion": "0.0000021"},
        "supported_parameters": ["reasoning", "reasoning_effort", "response_format", "structured_outputs", "temperature"],
        "default_parameters": {},
        "reasoning": {"mandatory": False, "default_enabled": True, "supported_efforts": ["high", "none"], "default_effort": "high"},
        "top_provider": {"max_completion_tokens": 262144},
    },
    "qwen/qwen3.8-flash": {
        "id": "qwen/qwen3.8-flash", "name": "Qwen3.8 Flash", "context_length": 1000000,
        "architecture": {"input_modalities": ["text", "image"]},
        "pricing": {"prompt": "0.00000015", "completion": "0.00000047"},
        "supported_parameters": ["reasoning", "response_format", "structured_outputs", "temperature"],
        "default_parameters": {},
        "reasoning": {"mandatory": False, "default_enabled": True, "supports_max_tokens": True},
        "top_provider": {"max_completion_tokens": 131072},
    },
    "google/gemma-4-31b-it": {
        "id": "google/gemma-4-31b-it", "name": "Gemma 4 31B", "context_length": 262144,
        "architecture": {"input_modalities": ["text", "image"]},
        "pricing": {"prompt": "0.0000002", "completion": "0.0000004"},
        "supported_parameters": ["max_tokens", "response_format", "structured_outputs", "temperature", "top_p"],
        "default_parameters": {"temperature": 1, "top_p": 0.95},
        "reasoning": {"mandatory": False, "default_enabled": False},
        "top_provider": {"max_completion_tokens": 16384},
    },
}
OPENROUTER = "https://openrouter.ai/api/v1"


class TuningBase(unittest.TestCase):
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
        member = f"member{uuid.uuid4().hex[:6]}"
        cls.client.post("/api/admin/users", headers=cls.h, json={"username": member, "password": "member-password-123"})
        mtok = cls.client.post("/api/auth/login", json={"username": member, "password": "member-password-123"}).json()["token"]
        cls.mh = {"X-Session-Token": mtok}
        cls.client.cookies.clear()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        from app.ai_tuning import service
        self.service = service
        service._cache.update(at=None, failed_at=None, models=None)
        service._warned.clear()
        p = mock.patch.object(service, "_fetch_catalogue", side_effect=lambda: copy.deepcopy(CATALOGUE))
        self.fetch = p.start()
        self.addCleanup(p.stop)
        self.addCleanup(service._cache.update, at=None, failed_at=None, models=None)
        self._ai_page(OPENROUTER, "anthropic/claude-haiku-5.5")
        self.service.set_settings(dict(self.service.DEFAULTS))

    def _ai_page(self, base_url, model, timeout="600"):
        conn = self.get_db()
        for k, v in (("ai_base_url", base_url), ("ai_model", model), ("ai_api_key", "sk-test"), ("ai_timeout", timeout)):
            conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        conn.commit()
        conn.close()


class EffortRules(TuningBase):
    def test_defaults_and_validation(self):
        self.assertEqual(self.service.get_settings(), {"scan": "", "cleanup": "", "guide": "high", "ballband": "medium"})
        self.assertEqual(self.service.set_settings({"guide": "XHIGH "})["guide"], "xhigh")
        for bad in ({"guide": "extreme"}, {"teapot": "high"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.service.set_settings(bad)

    def test_nearest_offered_effort(self):
        n = self.service.nearest_effort
        self.assertEqual(n("high", ["max", "xhigh", "high", "medium", "low", "none"]), "high")
        self.assertEqual(n("medium", ["high", "none"]), "high")     # Mistral Large 4 offers only high or off
        self.assertEqual(n("low", ["high", "none"]), "high")        # never silently switches thinking off
        self.assertEqual(n("none", ["high", "none"]), "none")       # unless asked
        self.assertEqual(n("max", ["xhigh", "high", "medium", "low", "minimal"]), "xhigh")
        self.assertEqual(n("medium", ["low", "high"]), "high")      # a tie goes to the stronger one

    def test_effort_sent_only_when_the_model_offers_it(self):
        e = self.service.effective_effort
        self.assertEqual(e("guide", OPENROUTER, "anthropic/claude-haiku-5.5"), "high")
        self.assertEqual(e("ballband", OPENROUTER, "anthropic/claude-haiku-5.5"), "medium")
        self.assertIsNone(e("scan", OPENROUTER, "anthropic/claude-haiku-5.5"))           # empty = model default
        self.assertEqual(e("ballband", OPENROUTER, "mistralai/mistral-large-4-0"), "high")
        self.assertIsNone(e("guide", OPENROUTER, "qwen/qwen3.8-flash"))                  # reasons, lists no levels
        self.assertIsNone(e("guide", OPENROUTER, "google/gemma-4-31b-it"))               # does not reason
        self.assertIsNone(e("guide", OPENROUTER, "someone/unknown-model"))
        self.assertIsNone(e("guide", "http://host.docker.internal:11434/v1", "llava"))   # not OpenRouter: nothing extra
        self.assertIsNone(e("guide", "https://openrouter.ai.evil.example/api/v1", "anthropic/claude-haiku-5.5"))

    def test_model_list_failure_falls_back_to_model_default_and_backs_off(self):
        self.fetch.side_effect = OSError("Cloudflare says no")
        self.assertIsNone(self.service.effective_effort("guide", OPENROUTER, "anthropic/claude-haiku-5.5"))
        self.service.effective_effort("guide", OPENROUTER, "anthropic/claude-haiku-5.5")
        self.assertEqual(self.fetch.call_count, 1)  # not refetched on every request after a failure

    def test_works_on_a_machine_that_has_just_started(self):
        # time.monotonic() counts from boot; CI runners are often up for under two minutes.
        with mock.patch.object(self.service.time, "monotonic", return_value=5.0):
            self.assertEqual(self.service.effective_effort("guide", OPENROUTER, "anthropic/claude-haiku-5.5"), "high")
        self.assertEqual(self.fetch.call_count, 1)

    def test_model_facts(self):
        info = self.service.model_info("anthropic/claude-haiku-5.5")
        self.assertEqual(info["reasoning"], {"supported": True, "efforts": ["none", "low", "medium", "high", "xhigh", "max"],
                                             "default": "medium", "mandatory": False})
        self.assertFalse(info["temperature"])  # Claude 5.5 ignores the scan and cleanup temperatures
        self.assertTrue(info["image_input"] and info["structured_outputs"])
        self.assertEqual((info["price_in"], info["price_out"], info["max_output_tokens"]), (0.1, 0.5, 128000))
        g = self.service.model_info("google/gemma-4-31b-it")
        self.assertTrue(g["temperature"])
        self.assertEqual(g["default_temperature"], 1)
        self.assertFalse(g["reasoning"]["supported"])


class UpstreamRequests(TuningBase):
    """Upstream's page scan and cleanup bodies get the effort for their feature, and nothing when it is unset."""

    def _body(self, call):
        from app.ai import jobs as upstream
        sent = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "text"}}], "usage": {}}

        async def fake_post(self_client, url, headers=None, json=None, **kw):
            sent.update(json)
            return FakeResponse()

        cfg = {"ai_base_url": OPENROUTER, "ai_model": "anthropic/claude-haiku-5.5", "ai_api_key": "k"}
        with mock.patch("httpx.AsyncClient.post", new=fake_post), \
             mock.patch.object(upstream, "_image_payload_for_path", return_value={"type": "text", "text": "img"}):
            if call == "scan":
                asyncio.run(upstream._call_ai_vision_page_scan(Path("/nonexistent.jpg"), 1, 1, "en", cfg, 30))
            else:
                asyncio.run(upstream._call_ai_page_cleanup("raw", 1, 1, "en", cfg, 30))
        return sent

    def test_scan_and_cleanup(self):
        self.assertNotIn("reasoning", self._body("scan"))  # default: the model's own effort, as upstream had it
        self.service.set_settings({"scan": "low", "cleanup": "minimal"})
        self.assertEqual(self._body("scan")["reasoning"], {"effort": "low"})
        self.assertEqual(self._body("cleanup")["reasoning"], {"effort": "low"})  # Haiku has no "minimal": nearest


class GuidedBuilds(TuningBase):
    def _job(self, recipe_id):
        from app.fork_migrations import ensure_fork_schema
        ensure_fork_schema()
        job_id = str(uuid.uuid4())
        conn = self.get_db()
        conn.execute("INSERT INTO guide_jobs (id, recipe_id, status, created_at) VALUES (?, ?, 'queued', '2026-11-15T00:00:00')",
                     (job_id, recipe_id))
        conn.commit()
        conn.close()
        return job_id

    def test_uses_the_ai_page_model_effort_and_timeout_and_keeps_the_reason_for_admins(self):
        from app.guided import jobs
        recipe_id = f"r-{uuid.uuid4().hex[:8]}"
        job_id = self._job(recipe_id)
        self._ai_page(OPENROUTER, "mistralai/mistral-large-4-0", timeout="900")
        self.service.set_settings({"guide": "medium"})
        seen = {}

        class FakeClient:
            def __init__(self, cfg):
                seen["cfg"] = cfg

            def close(self):
                pass

        def crash(*a, **kw):
            raise TypeError("'str' object is not subscriptable")

        with mock.patch.object(jobs.ai, "Client", FakeClient), mock.patch.object(jobs, "build_guide", crash):
            jobs._run(job_id)
        cfg = seen["cfg"]
        self.assertEqual((cfg.model, cfg.reasoning_effort, cfg.timeout), ("mistralai/mistral-large-4-0", "high", 900.0))

        admin = self.client.get(f"/api/guided/recipes/{recipe_id}", headers=self.h).json()["job"]
        self.assertEqual(admin["status"], "failed")
        self.assertIn("TypeError: 'str' object is not subscriptable", admin["error_detail"])
        self.assertIn("guided/jobs.py", admin["error_detail"])
        member = self.client.get(f"/api/guided/recipes/{recipe_id}", headers=self.mh).json()["job"]
        self.assertEqual(member["error_detail"], "")
        self.assertEqual(member["error"], admin["error"])

    def test_model_is_no_longer_set_on_knitting_upgrades(self):
        self.assertEqual(self.client.put("/api/fork/settings", json={"guide_model": "x/y"}, headers=self.h).status_code, 400)
        self.assertEqual(self.client.put("/api/guided/settings", json={"model": "x/y"}, headers=self.h).status_code, 400)
        self.assertEqual(self.client.get("/api/fork/settings", headers=self.h).json()["guide_model"], "anthropic/claude-haiku-5.5")


class TuningApi(TuningBase):
    def test_admin_only(self):
        self.assertEqual(self.client.get("/api/fork/ai/tuning", headers=self.mh).status_code, 403)
        self.assertEqual(self.client.put("/api/fork/ai/tuning", json={"settings": {"guide": "max"}}, headers=self.mh).status_code, 403)

    def test_read_and_save(self):
        r = self.client.get("/api/fork/ai/tuning", params={"model": "mistralai/mistral-large-4-0"}, headers=self.h).json()
        self.assertTrue(r["openrouter"] and r["catalogue_ok"])
        self.assertEqual(r["info"]["reasoning"]["efforts"], ["none", "high"])
        self.assertEqual({p["id"] for p in r["prompts"]}, {"guide_outline", "guide_section", "guide_picture", "ballband"})
        r = self.client.put("/api/fork/ai/tuning", json={"settings": {"guide": "xhigh", "scan": ""}}, headers=self.h)
        self.assertEqual(r.json()["settings"]["guide"], "xhigh")
        self.assertEqual(self.client.put("/api/fork/ai/tuning", json={"settings": {"guide": "lots"}}, headers=self.h).status_code, 400)

    def test_never_fetches_the_address_typed_on_the_page(self):
        r = self.client.get("/api/fork/ai/tuning", params={"model": "m", "base_url": "http://169.254.169.254/latest"},
                            headers=self.h).json()
        self.assertFalse(r["openrouter"])
        self.assertIsNone(r["info"])
        self.fetch.assert_not_called()


class AnswerShape(unittest.TestCase):
    """A model that ignores the schema gets told what was wrong and one more try; then the build fails cleanly."""

    def _client(self, answers):
        from app.guide_builder import ai
        c = ai.Client(ai.AIConfig(api_key="k"))
        posts = []

        def fake_post(body):
            posts.append(body)
            return {"_status": 200, "choices": [{"message": {"content": json.dumps(answers.pop(0))}, "finish_reason": "stop"}]}

        c._post = fake_post
        return c, posts

    def test_wrong_shape_is_retried_then_refused(self):
        sys.path.insert(0, str(Path(__file__).parent))
        import test_guide_builder_pipeline as samples
        from app.guide_builder import ai, schemas
        bad = copy.deepcopy(samples.OUTLINE)
        bad["sections"] = "Brim, Crown"
        c, posts = self._client([bad, copy.deepcopy(samples.OUTLINE)])
        self.assertEqual(c.json("sys", [], schemas.AI_OUTLINE, "pattern_outline").data["sections"][0]["name"], "Brim")
        self.assertIn("did not match the schema", posts[1]["messages"][0]["content"])
        c, _ = self._client([bad, bad])
        with self.assertRaises(ai.AIError):
            c.json("sys", [], schemas.AI_OUTLINE, "pattern_outline")


if __name__ == "__main__":
    unittest.main()
