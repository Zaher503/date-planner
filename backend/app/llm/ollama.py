"""Ollama client (the shared recipebox-ollama container). Callers hold the GPU lock."""
import json

import httpx

from app.config import get_settings

KEEP_ALIVE = "2m"  # a burst of links reuses the loaded model; Recipe Box unloads it before its own jobs


class LLMError(RuntimeError):
    pass


def chat_json(system: str, user: str, schema: dict, *, images: list[str] | None = None,
              model: str | None = None, timeout: float = 300) -> dict:
    """One chat turn constrained to a JSON schema. images are base64 strings."""
    s = get_settings()
    msg = {"role": "user", "content": user}
    if images:
        msg["images"] = images
    body = {
        "model": model or s.llm_model, "stream": False, "think": False, "format": schema,
        "keep_alive": KEEP_ALIVE, "options": {"temperature": 0, "num_ctx": 8192},
        "messages": [{"role": "system", "content": system}, msg],
    }
    try:
        r = httpx.post(f"{s.ollama_url}/api/chat", json=body, timeout=timeout)
        r.raise_for_status()
        content = r.json()["message"]["content"]
        return json.loads(content)
    except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
        raise LLMError(f"local model call failed: {type(e).__name__}: {e}") from e
