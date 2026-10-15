"""Robots.txt handling and the real API request code, with the network mocked out."""
import json
import urllib.robotparser

import pytest

from scraper import fetch, llm

# Excerpt of gambling.com/robots.txt (October 2026).
ROBOTS = """
User-agent: Fetch
Disallow: /
User-agent: wget
Disallow: /
User-agent: *
Disallow: /go/
Disallow: /uk/p/best-online-casinos
"""


def parser():
    p = urllib.robotparser.RobotFileParser()
    p.parse(ROBOTS.splitlines())
    return p


def test_our_bonus_page_is_allowed():
    assert parser().can_fetch(fetch.USER_AGENT, "https://www.gambling.com/uk/online-casinos/bonus")


def test_disallowed_paths_are_respected():
    p = parser()
    assert not p.can_fetch(fetch.USER_AGENT, "https://www.gambling.com/go/uk/mr-vegas/offer/1")
    assert not p.can_fetch(fetch.USER_AGENT, "https://www.gambling.com/uk/p/best-online-casinos")


class FakeResponse:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text
        self.ok = 200 <= status < 300

    def json(self):
        return self._payload


def test_fetch_stops_on_403_instead_of_bypassing(monkeypatch):
    def fake_get(url, **kw):
        return FakeResponse(200, text="") if url.endswith("robots.txt") else FakeResponse(403, text="denied")
    monkeypatch.setattr(fetch.requests, "get", fake_get)
    with pytest.raises(fetch.BlockedError):
        fetch.fetch_html("https://example.com/page")


ANSWER = {"welcome_bonus": "100% up to £50", "wagering_multiplier": 10, "min_deposit_amount": 10, "currency": "GBP"}


def test_openai_compatible_request(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, body=json)
        return FakeResponse(200, {"choices": [{"message": {"content": __import__("json").dumps(ANSWER)}}]})

    monkeypatch.setattr(llm.requests, "post", fake_post)
    call, label = llm.make_caller()
    assert llm.extract_terms(call, "X", "terms") == ANSWER
    assert seen["url"].endswith("/chat/completions")
    assert seen["headers"]["Authorization"] == "Bearer k"
    assert seen["body"]["temperature"] == 0
    assert label.startswith("groq/")


def test_anthropic_request(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, body=json)
        return FakeResponse(200, {"content": [{"type": "text", "text": __import__("json").dumps(ANSWER)}]})

    monkeypatch.setattr(llm.requests, "post", fake_post)
    call, label = llm.make_caller()
    assert llm.extract_terms(call, "X", "terms") == ANSWER
    assert seen["url"].endswith("/messages") and seen["headers"]["x-api-key"] == "k"
    assert seen["body"]["model"] == "some-model" and label == "anthropic/some-model"


def test_timeout_is_retried_and_bad_key_is_not(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    replies = [llm.requests.Timeout("slow"), FakeResponse(503, text="busy"),
               FakeResponse(200, {"choices": [{"message": {"content": json.dumps(ANSWER)}}]})]

    def fake_post(*a, **k):
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(llm.requests, "post", fake_post)
    call, _ = llm.make_caller()
    assert llm.extract_terms(call, "X", "terms") == ANSWER

    calls = []
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: calls.append(1) or FakeResponse(401, text="bad key"))
    with pytest.raises(RuntimeError, match="401"):
        call("s", "t")
    assert len(calls) == 1  # no pointless retries on a wrong key


def test_rate_limit_is_retried(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    replies = [FakeResponse(429, text="slow down"),
               FakeResponse(200, {"choices": [{"message": {"content": json.dumps(ANSWER)}}]})]
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: replies.pop(0))
    call, _ = llm.make_caller()
    assert llm.extract_terms(call, "X", "terms") == ANSWER