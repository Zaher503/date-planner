import json

import httpx
import pytest

from app.config import get_settings
from app.llm import ollama
from app.llm.ollama import LLMError, chat_json, parse_json_reply

SCHEMA = {"type": "object", "properties": {"items": {"type": "array"}}}


def test_parse_plain_fenced_and_chatty_replies():
    assert parse_json_reply('{"a": 1}') == {"a": 1}
    assert parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_reply('<think>hmm {x}</think>Sure! {"a": 1} Hope that helps') == {"a": 1}
    with pytest.raises(json.JSONDecodeError):
        parse_json_reply("no json here")


def _use_openrouter(monkeypatch, key="k"):
    s = get_settings()
    monkeypatch.setattr(s, "llm_provider", "openrouter")
    monkeypatch.setattr(s, "openrouter_api_key", key)


def test_chat_json_sends_schema_and_parses(monkeypatch):
    _use_openrouter(monkeypatch)
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, body=json, headers=headers)
        return httpx.Response(200, request=httpx.Request("POST", url),
                              json={"choices": [{"message": {"content": '```json\n{"items": []}\n```'}}]})

    monkeypatch.setattr(ollama.httpx, "post", fake_post)
    assert chat_json("sys", "text", SCHEMA) == {"items": []}
    assert seen["url"].endswith("/chat/completions")
    assert seen["body"]["model"] == "nvidia/nemotron-3.5-lightning"
    assert seen["headers"]["Authorization"] == "Bearer k"
    assert "response_format" not in seen["body"]
    assert '"items"' in seen["body"]["messages"][0]["content"]


def test_openrouter_errors_become_llm_errors(monkeypatch):
    _use_openrouter(monkeypatch)
    monkeypatch.setattr(ollama.httpx, "post", lambda url, **kw: httpx.Response(
        429, request=httpx.Request("POST", url), json={"error": {"code": 429, "message": "slow down"}}))
    with pytest.raises(LLMError):
        chat_json("sys", "text", SCHEMA)


def test_openrouter_needs_key_and_rejects_images(monkeypatch):
    _use_openrouter(monkeypatch, key="")
    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        chat_json("sys", "text", SCHEMA)
    _use_openrouter(monkeypatch)
    with pytest.raises(LLMError, match="text only"):
        chat_json("sys", "text", SCHEMA, images=["abc"])
