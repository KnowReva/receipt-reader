"""Talking to Ollama (https://ollama.com), which runs the AI model on your own computer.

One request: POST /api/chat with the image (base64), the prompt and the JSON schema in `format`.
Only the standard library is used, so there is nothing extra to install."""

import json
import os
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("RECEIPT_MODEL", "qwen2.5vl:7b")
# The context window holds the prompt, the image's tokens and the answer. Not sent unless you set it:
# a request with a different size than the server's makes Ollama reload the whole model, and if other
# programs share Ollama (Dhoon runs it with 16-32k) it reloads again for them: minutes each time. If
# your Ollama runs with its plain default (4096) and long receipts get cut off, set RECEIPT_CONTEXT=8192.
CONTEXT = int(os.environ.get("RECEIPT_CONTEXT", "0") or 0)


class ModelError(RuntimeError):
    """Ollama couldn't be used (not running, no model, too slow): reading stops."""


class BadAnswer(ModelError):
    """Ollama answered, but not with a complete JSON object: worth one more look."""


def chat(messages: list[dict], schema: dict, model: str = DEFAULT_MODEL, url: str = DEFAULT_URL,
         timeout: float = 600) -> dict:  # fmt: skip
    """Send one chat to Ollama and return the JSON object it answered with."""
    body = {
        "model": model,
        "messages": messages,
        "format": schema,  # structured outputs: the answer must match this JSON schema
        "stream": False,
        "think": False,  # thinking models (gemma4, qwen3...) answer straight away: many times faster
        "options": {"temperature": 0,  # the same receipt should give the same answer every time
                    **({"num_ctx": CONTEXT} if CONTEXT else {})},
    }
    request = urllib.request.Request(f"{url.rstrip('/')}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})  # fmt: skip
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            reply = json.loads(response.read())
    except TimeoutError:
        raise ModelError(f"Ollama took longer than {timeout:.0f} seconds; try a smaller model (--model qwen2.5vl:3b)") from None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="ignore")[:300]
        if e.code == 404 and "not found" in detail:
            raise ModelError(f"Ollama doesn't have the model '{model}' yet. Run: ollama pull {model}") from None
        raise ModelError(f"Ollama answered {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise ModelError(f"Ollama took longer than {timeout:.0f} seconds; try a smaller model (--model qwen2.5vl:3b)") from None
        raise ModelError(f"Can't reach Ollama at {url} ({e.reason}). Is it running? Try: ollama serve") from None
    # "stop" means the model finished. Anything else (e.g. "length") means the answer was cut off, and a
    # cut-off answer is broken JSON, or worse, valid JSON with the last items missing.
    reason = reply.get("done_reason") or "stop"
    if reason != "stop":
        raise BadAnswer(f"the model's answer was cut off (done_reason: {reason}); a bigger context may help: "
                        f"RECEIPT_CONTEXT={CONTEXT * 2 if CONTEXT else 8192}")  # fmt: skip
    try:
        answer = json.loads(reply["message"]["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        raise BadAnswer(f"the model's answer wasn't valid JSON ({e})") from None
    if not isinstance(answer, dict):
        raise BadAnswer("the model's answer wasn't a JSON object")
    return answer
