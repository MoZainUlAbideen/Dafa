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
    assert p["reasoning_effort"] == "low" and p["max_tokens"] >= 2000


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
