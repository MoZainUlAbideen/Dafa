"""Minimal Groq client (OpenAI-compatible chat endpoint) over httpx.

Includes the two things the free tier needs, both learned on EdgarIQ:
  - client-side throttling so bursts don't trip the per-minute limit
  - retry with backoff on HTTP 429 / 5xx
It also records token usage so the API can log cost per request (LLMOps).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field

import httpx

from dafa.config import settings


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latencies_ms: list[int] = field(default_factory=list)


class GroqClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, min_interval_s: float = 0.5):
        self.api_key = api_key if api_key is not None else settings.groq_api_key
        self.model = model or settings.groq_model
        self.min_interval_s = min_interval_s
        self._last = 0.0
        self._lock = threading.Lock()
        self._http = httpx.Client(base_url=settings.groq_base_url, timeout=45)

    def _throttle(self) -> None:
        with self._lock:
            wait = self.min_interval_s - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def chat_json(self, system: str, user: str, usage: Usage | None = None, temperature: float = 0.1, max_tokens: int = 1200) -> dict:
        """Call the model and parse a JSON object from its reply."""
        if not self.api_key:
            raise LLMError("GROQ_API_KEY is not set")
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        last_err = ""
        for attempt in range(4):
            self._throttle()
            t0 = time.monotonic()
            try:
                r = self._http.post("/chat/completions", json=payload, headers={"Authorization": f"Bearer {self.api_key}"})
            except httpx.HTTPError as e:
                last_err = str(e)
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code == 429 or r.status_code >= 500:
                retry_after = float(r.headers.get("retry-after", 2 * (attempt + 1)))
                last_err = f"HTTP {r.status_code}"
                time.sleep(min(retry_after, 10))
                continue
            if r.status_code != 200:
                raise LLMError(f"Groq HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            if usage is not None:
                u = data.get("usage", {})
                usage.calls += 1
                usage.prompt_tokens += u.get("prompt_tokens", 0)
                usage.completion_tokens += u.get("completion_tokens", 0)
                usage.latencies_ms.append(int((time.monotonic() - t0) * 1000))
            content = data["choices"][0]["message"]["content"]
            return parse_json(content)
        raise LLMError(f"Groq failed after retries: {last_err}")


def parse_json(content: str) -> dict:
    """Parse JSON even if the model wrapped it in ``` fences or added prose."""
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end > start:
            return json.loads(content[start : end + 1])
        raise LLMError(f"Model did not return JSON: {content[:200]}")
