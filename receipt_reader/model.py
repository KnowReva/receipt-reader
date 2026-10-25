"""Talking to Ollama (https://ollama.com), which runs the AI model on your own computer.

One request: POST /api/chat with the image (base64), the prompt and the JSON schema in `format`.
Only the standard library is used, so there is nothing extra to install."""

import json
import os
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("RECEIPT_MODEL", "qwen2.5vl:7b")


class ModelError(RuntimeError):
    pass


def chat(messages: list[dict], schema: dict, model: str = DEFAULT_MODEL, url: str = DEFAULT_URL,
         timeout: float = 600) -> dict:  # fmt: skip
    """Send one chat to Ollama and return the JSON object it answered with."""
    body = {
        "model": model,
        "messages": messages,
        "format": schema,  # structured outputs: the answer must match this JSON schema
        "stream": False,
        "options": {"temperature": 0},  # the same receipt should give the same answer every time
    }
    request = urllib.request.Request(f"{url.rstrip('/')}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})  # fmt: skip
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            reply = json.loads(response.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:300]
        if e.code == 404 and "not found" in detail:
            raise ModelError(f"Ollama doesn't have the model '{model}' yet. Run: ollama pull {model}") from None
        raise ModelError(f"Ollama answered {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise ModelError(f"Can't reach Ollama at {url} ({e.reason}). Is it running? Try: ollama serve") from None
    try:
        return json.loads(reply["message"]["content"])
    except (KeyError, json.JSONDecodeError) as e:
        raise ModelError(f"The model's answer wasn't valid JSON ({e})") from None
