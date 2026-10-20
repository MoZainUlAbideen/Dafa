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

    @property
    def is_reasoning_model(self) -> bool:
        """gpt-oss / qwen3 "think" before answering, and those hidden reasoning
        tokens count against max_tokens."""
        m = self.model.lower()
        return "gpt-oss" in m or "qwen3" in m

    def build_payload(self, system: str, user: str, temperature: float, max_tokens: int) -> dict:
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self.is_reasoning_model:
            # Bug found in full evals with openai/gpt-oss-120b: budgets sized for a
            # non-reasoning model (300 / 1200) ran out during reasoning, so Groq
            # returned json_validate_failed "max completion tokens reached".
            payload["reasoning_effort"] = settings.reasoning_effort
            payload["max_tokens"] = max(max_tokens * 3, 2000)
        return payload

    def chat_json(self, system: str, user: str, usage: Usage | None = None, temperature: float = 0.1, max_tokens: int = 1200) -> dict:
        """Call the model and parse a JSON object from its reply."""
        if not self.api_key:
            raise LLMError("GROQ_API_KEY is not set")
        payload = self.build_payload(system, user, temperature, max_tokens)
        last_err = ""
        json_retry_done = False
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
            if r.status_code == 400 and "json_validate_failed" in r.text and not json_retry_done:
                # The model ran out of room or produced invalid JSON: retry once with double budget.
                json_retry_done = True
                payload = {**payload, "max_tokens": payload["max_tokens"] * 2}
                last_err = "json_validate_failed"
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
            content = data["choices"][0]["message"].get("content") or ""
            return parse_json(content)
        raise LLMError(f"Groq failed after retries: {last_err}")


def preflight(client: "GroqClient") -> None:
    """One tiny call before a batch run, so a wrong model name or key fails
    fast with a clear message instead of failing every eval case (found when
    Groq retired the default model and all 56 cases were marked FAIL)."""
    client.chat_json("Reply with JSON.", 'Return {"ok": true}', max_tokens=20)


def list_models(api_key: str | None = None) -> list[str]:
    key = api_key if api_key is not None else settings.groq_api_key
    r = httpx.get(f"{settings.groq_base_url}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
    r.raise_for_status()
    return sorted(m["id"] for m in r.json().get("data", []))


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


if __name__ == "__main__":  # uv run python -m dafa.llm.groq_client  -> lists the models your key can use
    print("\n".join(list_models()))
