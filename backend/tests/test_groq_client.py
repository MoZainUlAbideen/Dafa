"""Groq client behaviour, tested with httpx's MockTransport (no network)."""

import json

import httpx

from dafa.llm.groq_client import GroqClient


def client_with(handler, model="openai/gpt-oss-120b"):
    c = GroqClient(api_key="test", model=model, min_interval_s=0)
    c._http = httpx.Client(base_url="https://api.groq.test/openai/v1", transport=httpx.MockTransport(handler))
    return c


def ok(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {}})


def test_reasoning_model_gets_effort_and_bigger_budget():
    c = client_with(lambda r: ok("{}"))
    p = c.build_payload("s", "u", 0.1, 300)
    assert p["reasoning_effort"] == "low" and p["max_tokens"] >= 1200


def test_non_reasoning_model_payload_unchanged():
    c = client_with(lambda r: ok("{}"), model="some-llama-70b")
    p = c.build_payload("s", "u", 0.1, 300)
    assert "reasoning_effort" not in p and p["max_tokens"] == 300


def test_json_validate_failed_retries_once_with_double_budget():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body["max_tokens"])
        if len(seen) == 1:
            return httpx.Response(400, json={"error": {"code": "json_validate_failed",
                                                        "failed_generation": "max completion tokens reached"}})
        return ok('{"answer": "fine"}')

    assert client_with(handler).chat_json("s", "u", max_tokens=1200) == {"answer": "fine"}
    assert seen[1] == seen[0] * 2


def test_json_wrapped_in_prose_is_parsed():
    assert client_with(lambda r: ok('Here: {"ok": true} done')).chat_json("s", "u") == {"ok": True}


def test_429_honours_retry_after(monkeypatch):
    sleeps = []
    monkeypatch.setattr("dafa.llm.groq_client.time.sleep", lambda s: sleeps.append(s))
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "30"}, json={"error": {"code": "rate_limit_exceeded"}})
        return ok('{"ok": true}')

    assert client_with(handler).chat_json("s", "u") == {"ok": True}
    assert any(s >= 30 for s in sleeps)  # waited the full window, not 10s


def test_daily_limit_raises_immediately(monkeypatch):
    from dafa.llm.groq_client import RateLimitExhausted
    monkeypatch.setattr("dafa.llm.groq_client.time.sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"error": {"message": "Rate limit reached on tokens per day (TPD): Limit 200000"}})

    try:
        client_with(handler).chat_json("s", "u")
        raise AssertionError("should have raised")
    except RateLimitExhausted:
        pass
    assert len(calls) == 1  # no pointless retries


def test_low_remaining_tokens_schedules_a_wait(monkeypatch):
    from dafa.llm.groq_client import parse_duration
    assert parse_duration("1m2.5s") == 62.5 and parse_duration("450ms") == 0.45
    c = client_with(lambda r: httpx.Response(200, headers={"x-ratelimit-remaining-tokens": "900", "x-ratelimit-reset-tokens": "20s"},
                                              json={"choices": [{"message": {"content": "{}"}}], "usage": {}}))
    c.chat_json("s", "u")
    import time
    assert c._resume_at - time.monotonic() > 15  # next call will wait for the minute to reset


def test_long_waits_are_reported(monkeypatch):
    monkeypatch.setattr("dafa.llm.groq_client.time.sleep", lambda s: None)
    seen = []
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "20"}, json={"error": {"message": "tokens per minute"}})
        return ok("{}")

    c = client_with(handler)
    c.on_wait = lambda s, why: seen.append((round(s), why))
    c.chat_json("s", "u")
    assert seen and seen[0][0] >= 20 and "429" in seen[0][1]


def test_api_client_gives_up_fast_instead_of_waiting_a_minute(monkeypatch):
    from dafa.llm.groq_client import LLMError
    slept = []
    monkeypatch.setattr("dafa.llm.groq_client.time.sleep", lambda s: slept.append(s))
    c = client_with(lambda r: httpx.Response(429, headers={"retry-after": "40"}, json={"error": {"message": "tokens per minute"}}))
    c.max_wait_s = 8
    try:
        c.chat_json("s", "u")
        raise AssertionError("should have raised")
    except LLMError as e:
        assert "would need to wait" in str(e)
    assert not any(s > 8 for s in slept)
