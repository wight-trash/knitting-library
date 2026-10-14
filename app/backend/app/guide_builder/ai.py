"""A small client for OpenAI-compatible chat completions (OpenRouter), as the guide builder needs it.

* JSON answers: a strict JSON schema first; if the provider refuses the schema, plain JSON mode with the schema in the
  prompt. The answer is always parsed and returned as a dict; checking it is the caller's job.
* Retries on rate limits and server errors, with back-off.
* Usage and cost (OpenRouter reports cost) are returned with every answer.
* Privacy: providers that may train on or keep the data are excluded (OpenRouter `data_collection: deny`).
* No `temperature`: the newer Claude and GPT providers refuse it.
"""
from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass, field

import httpx

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class AIError(RuntimeError):
    """The model could not give a usable answer. The message is safe to show in logs, never contains the key."""


@dataclass
class AIConfig:
    api_key: str
    model: str = "anthropic/claude-haiku-5.5"
    base_url: str = DEFAULT_BASE_URL
    max_tokens: int = 64000
    reasoning_effort: str | None = "low"   # "low", "medium", "high" or None for the provider default
    timeout: float = 600.0
    retries: int = 3
    app_title: str = "Knitting Library"


@dataclass
class Answer:
    data: dict
    mode: str                         # "strict" or "json_object"
    usage: dict = field(default_factory=dict)
    seconds: float = 0.0
    finish_reason: str | None = None

    @property
    def cost(self) -> float:
        return float(self.usage.get("cost") or 0.0)


def image_part(jpeg: bytes) -> dict:
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}}


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


def _strip_fences(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    return re.sub(r"\s*```$", "", s)


class Client:
    def __init__(self, config: AIConfig):
        self.cfg = config
        self._http = httpx.Client(timeout=config.timeout)

    def close(self) -> None:
        self._http.close()

    def _post(self, body: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.cfg.api_key}", "X-Title": self.cfg.app_title}
        delay = 2.0
        last = ""
        for attempt in range(self.cfg.retries + 1):
            try:
                r = self._http.post(f"{self.cfg.base_url}/chat/completions", json=body, headers=headers)
            except httpx.HTTPError as exc:
                last = f"network error: {exc.__class__.__name__}"
            else:
                if r.status_code in (429, 500, 502, 503, 504):
                    last = f"HTTP {r.status_code}"
                else:
                    try:
                        data = r.json()
                    except ValueError:
                        raise AIError(f"HTTP {r.status_code}: not JSON") from None
                    data["_status"] = r.status_code
                    return data
            if attempt < self.cfg.retries:
                time.sleep(delay)
                delay *= 2
        raise AIError(f"gave up after {self.cfg.retries + 1} tries ({last})")

    def json(self, system: str, content: list[dict], schema: dict, name: str, *, max_tokens: int | None = None,
             reasoning_effort: str | None = "default") -> Answer:
        """Ask for a JSON answer matching `schema`. Raises AIError when no usable JSON comes back."""
        effort = self.cfg.reasoning_effort if reasoning_effort == "default" else reasoning_effort
        base = {
            "model": self.cfg.model,
            "max_tokens": max_tokens or self.cfg.max_tokens,
            "usage": {"include": True},
            "provider": {"data_collection": "deny", "require_parameters": True},
        }
        if effort:
            base["reasoning"] = {"effort": effort}
        start = time.time()
        strict = {**base, "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
                  "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}}
        data = self._post(strict)
        mode = "strict"
        if data.get("error") or data["_status"] >= 400:
            loose_system = system + "\n\nReply with JSON only, matching this JSON schema:\n" + json.dumps(schema)
            loose = {**base, "messages": [{"role": "system", "content": loose_system}, {"role": "user", "content": content}],
                     "response_format": {"type": "json_object"}}
            data = self._post(loose)
            mode = "json_object"
        if data.get("error"):
            msg = data["error"].get("message") if isinstance(data["error"], dict) else str(data["error"])
            raise AIError(f"provider error: {str(msg)[:200]}")
        choice = (data.get("choices") or [{}])[0]
        finish = choice.get("finish_reason")
        text = (choice.get("message") or {}).get("content") or ""
        if finish == "length":
            raise AIError("the answer was cut off (output limit reached)")
        try:
            parsed = json.loads(_strip_fences(text))
        except json.JSONDecodeError as exc:
            raise AIError(f"the answer was not valid JSON ({exc.msg})") from None
        if not isinstance(parsed, dict):
            raise AIError("the answer was not a JSON object")
        return Answer(parsed, mode, data.get("usage") or {}, round(time.time() - start, 1), finish)

    def text(self, system: str, content: list[dict], *, max_tokens: int = 8000, reasoning_effort: str | None = None) -> Answer:
        """Ask for plain text (used to transcribe picture pages). data = {"text": ...}."""
        body = {"model": self.cfg.model, "max_tokens": max_tokens, "usage": {"include": True},
                "provider": {"data_collection": "deny"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
        if reasoning_effort:
            body["reasoning"] = {"effort": reasoning_effort}
        start = time.time()
        data = self._post(body)
        if data.get("error"):
            msg = data["error"].get("message") if isinstance(data["error"], dict) else str(data["error"])
            raise AIError(f"provider error: {str(msg)[:200]}")
        choice = (data.get("choices") or [{}])[0]
        return Answer({"text": (choice.get("message") or {}).get("content") or ""}, "text", data.get("usage") or {},
                      round(time.time() - start, 1), choice.get("finish_reason"))
