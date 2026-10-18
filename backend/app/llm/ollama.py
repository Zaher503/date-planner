"""Client for the shared AI hub (Ollama API through the gateway, which queues GPU work).

Before a call, the hub is asked how long the line is; callers that registered a listener with
waiting() hear about it, so a job can show "waiting for the AI, about 40 s" instead of looking stuck.
"""
import json
import logging
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
KEEP_ALIVE = "2m"  # a burst of links reuses the loaded model
CLIENT = "dates-worker"
# Jobs that are only worth telling someone about when the wait is noticeable
NOTE_AFTER_SECONDS = 5.0

_listener: ContextVar = ContextVar("ai_wait_listener", default=None)


class LLMError(RuntimeError):
    pass


@contextmanager
def waiting(listener):
    """Call listener(estimate) before each AI call that has to wait in line."""
    token = _listener.set(listener)
    try:
        yield
    finally:
        _listener.reset(token)


def describe(est: dict) -> str:
    wait = int(est.get("wait_seconds", 0))
    ahead = int(est.get("position", 0))
    when = f"about {wait} s" if wait < 90 else f"about {round(wait / 60)} min"
    return f"waiting for the AI ({ahead} ahead, {when})"


def estimate(kind: str, model: str | None = None, audio_seconds: float | None = None, priority: str = "low") -> dict | None:
    s = get_settings()
    params = {"kind": kind, "model": model or "", "priority": priority}
    if audio_seconds:
        params["audio_seconds"] = round(audio_seconds, 1)
    try:
        r = httpx.get(f"{s.ollama_url}/queue/estimate", params=params, timeout=3)
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError):
        return None  # an older Ollama without the hub in front: just carry on


def announce(kind: str, model: str | None = None, audio_seconds: float | None = None) -> None:
    listener = _listener.get()
    if listener is None:
        return
    est = estimate(kind, model, audio_seconds)
    if est and est.get("wait_seconds", 0) >= NOTE_AFTER_SECONDS:
        listener(est)


def headers(audio_seconds: float | None = None) -> dict:
    h = {"X-Client": CLIENT, "X-Priority": "low", "X-Queue-Ticket": uuid.uuid4().hex}
    if audio_seconds:
        h["X-Audio-Seconds"] = str(round(audio_seconds, 1))
    return h


THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S)


def parse_json_reply(content: str) -> dict:
    """The JSON object in a model reply that may add reasoning, code fences or chatter around it."""
    text = THINK_BLOCK.sub("", content or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise json.JSONDecodeError("no JSON object in the reply", text, 0)
    return json.loads(text[start:end + 1])


def chat_json_openrouter(system: str, user: str, schema: dict, *, model: str | None = None,
                         timeout: float = 300) -> dict:
    """Same contract as chat_json, through OpenRouter. The model advertises no response_format,
    so the schema goes into the prompt and the reply is parsed leniently; callers still validate."""
    s = get_settings()
    if not s.openrouter_api_key:
        raise LLMError("OPENROUTER_API_KEY is not set")
    model = model or s.openrouter_model
    prompt = (f"{system}\n\nReply with one JSON object only, no prose and no code fences, "
              f"that matches this JSON schema:\n{json.dumps(schema)}")
    # Reasoning off: the answer is a short JSON object, and thinking tokens would eat the budget
    body = {"model": model, "temperature": 0, "stream": False, "max_tokens": 6000, "reasoning": {"enabled": False},
            "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": user}]}
    try:
        r = httpx.post("https://openrouter.ai/api/v1/chat/completions", json=body, timeout=timeout,
                       headers={"Authorization": f"Bearer {s.openrouter_api_key}"})
        r.raise_for_status()
        return parse_json_reply(r.json()["choices"][0]["message"]["content"])
    except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        if isinstance(e, httpx.HTTPStatusError):
            e = httpx.HTTPError(f"{e.response.status_code} {e.response.text[:200]}")
        raise LLMError(f"openrouter call failed: {type(e).__name__}: {e}") from e


def chat_json(system: str, user: str, schema: dict, *, images: list[str] | None = None,
              model: str | None = None, timeout: float = 900) -> dict:
    """One chat turn constrained to a JSON schema. images are base64 strings."""
    s = get_settings()
    if s.llm_provider == "openrouter" and not images:
        # Text goes to OpenRouter; anything with images (screenshots, video frames) stays on the hub
        return chat_json_openrouter(system, user, schema, model=model, timeout=min(timeout, 300))
    model = model or s.llm_model
    msg = {"role": "user", "content": user}
    if images:
        msg["images"] = images
    body = {
        "model": model, "stream": False, "think": False, "format": schema,
        "keep_alive": KEEP_ALIVE, "options": {"temperature": 0, "num_ctx": 8192},
        "messages": [{"role": "system", "content": system}, msg],
    }
    announce("chat", model)
    try:
        # The timeout covers the wait in line as well as the answer
        r = httpx.post(f"{s.ollama_url}/api/chat", json=body, headers=headers(), timeout=timeout)
        r.raise_for_status()
        waited = r.headers.get("x-queue-wait-seconds")
        if waited and float(waited) > NOTE_AFTER_SECONDS:
            log.info("model call waited %s s in the AI queue", waited)
        content = r.json()["message"]["content"]
        return json.loads(content)
    except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
        raise LLMError(f"local model call failed: {type(e).__name__}: {e}") from e
