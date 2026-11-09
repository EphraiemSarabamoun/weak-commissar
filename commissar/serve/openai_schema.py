"""Parse OpenAI chat-completion requests and build OpenAI-shaped responses.

Pure functions with no torch or model dependency, so they are unit-tested
offline. Validation errors raise ApiError, which the HTTP layer turns into the
OpenAI error envelope {"error": {"message", "type", "param", "code"}}.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import settings

ALLOWED_ROLES = {"system", "user", "assistant", "tool"}
# Only this template switch is accepted: other apply_chat_template options (tokenize,
# chat_template, truncation, ...) would replace the model's template or break generation.
ALLOWED_TEMPLATE_KWARGS = {"enable_thinking"}
# torch.manual_seed accepts exactly this range.
SEED_MIN, SEED_MAX = -(2**63), 2**64 - 1


class ApiError(Exception):
    """A request the server rejects, carrying the HTTP status and OpenAI error fields."""

    def __init__(self, status: int, message: str, code: str | None = None, param: str | None = None,
                 err_type: str = "invalid_request_error"):
        super().__init__(message)
        self.status, self.message, self.code, self.param, self.err_type = status, message, code, param, err_type

    def body(self) -> dict:
        return {"error": {"message": self.message, "type": self.err_type, "param": self.param, "code": self.code}}


@dataclass
class ChatRequest:
    """A validated chat request; sampling fields already resolved to their defaults."""

    model: str
    messages: list[dict]
    temperature: float
    top_p: float
    max_tokens: int
    seed: int | None
    stop: list[str]
    stream: bool
    enable_thinking: bool

    @property
    def greedy(self) -> bool:
        """Temperature 0 means greedy decoding, which is deterministic."""
        return self.temperature == 0.0


def _number(body: dict, name: str, default: float, lo: float, hi: float) -> float:
    value = body.get(name)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiError(400, f"{name} must be a number", param=name)
    if not lo <= value <= hi:
        raise ApiError(400, f"{name} must be between {lo} and {hi}", param=name)
    return float(value)


def _content_text(content, index: int):
    """Accept string content or a list of text parts; reject images and other parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict) or part.get("type", "text") != "text" or not isinstance(part.get("text"), str):
                raise ApiError(400, f"messages[{index}].content: only text parts are supported", param="messages")
            parts.append(part["text"])
        return "".join(parts)
    if content is None:
        return ""
    raise ApiError(400, f"messages[{index}].content must be a string or a list of text parts", param="messages")


def _messages(body: dict) -> list[dict]:
    raw = body.get("messages")
    if not isinstance(raw, list) or not raw:
        raise ApiError(400, "messages must be a non-empty list", param="messages")
    out = []
    for i, msg in enumerate(raw):
        if not isinstance(msg, dict) or msg.get("role") not in ALLOWED_ROLES:
            raise ApiError(400, f"messages[{i}].role must be one of {sorted(ALLOWED_ROLES)}", param="messages")
        clean = {"role": msg["role"], "content": _content_text(msg.get("content"), i)}
        if msg["role"] == "assistant" and isinstance(msg.get("reasoning_content"), str):
            clean["reasoning_content"] = msg["reasoning_content"]
        out.append(clean)
    if not any(m["role"] == "user" for m in out):
        # Qwen3.5's own chat template raises without a user turn; say so plainly
        # rather than inventing one.
        raise ApiError(400, "Qwen3.5's chat template needs at least one user message", param="messages")
    return out


def parse_chat_request(body) -> ChatRequest:
    """Validate a /v1/chat/completions body and resolve defaults."""
    if not isinstance(body, dict):
        raise ApiError(400, "request body must be a JSON object")
    model = body.get("model")
    if not isinstance(model, str) or not model:
        raise ApiError(400, "model is required", param="model")
    n = body.get("n")
    if n is not None and n != 1:
        raise ApiError(400, "only n=1 is supported", param="n")

    max_tokens = body.get("max_completion_tokens", body.get("max_tokens"))
    if max_tokens is None:
        max_tokens = settings.DEFAULT_MAX_TOKENS
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= settings.MAX_MAX_TOKENS:
        raise ApiError(400, f"max_tokens must be an integer from 1 to {settings.MAX_MAX_TOKENS}", param="max_tokens")

    seed = body.get("seed")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int) or not SEED_MIN <= seed <= SEED_MAX):
        raise ApiError(400, f"seed must be an integer from {SEED_MIN} to {SEED_MAX}", param="seed")

    stop = body.get("stop") or []
    if isinstance(stop, str):
        stop = [stop]
    if (not isinstance(stop, list) or len(stop) > settings.MAX_STOP_SEQUENCES
            or not all(isinstance(s, str) and s for s in stop)):
        raise ApiError(400, f"stop must be a string or up to {settings.MAX_STOP_SEQUENCES} non-empty strings", param="stop")

    kwargs = body.get("chat_template_kwargs") or {}
    if not isinstance(kwargs, dict):
        raise ApiError(400, "chat_template_kwargs must be an object", param="chat_template_kwargs")
    unknown = sorted(set(kwargs) - ALLOWED_TEMPLATE_KWARGS)
    if unknown:
        raise ApiError(400, f"chat_template_kwargs may only set {sorted(ALLOWED_TEMPLATE_KWARGS)}; got {unknown}",
                       param="chat_template_kwargs")
    enable_thinking = bool(kwargs.get("enable_thinking", settings.DEFAULT_ENABLE_THINKING))

    return ChatRequest(
        model=model,
        messages=_messages(body),
        temperature=_number(body, "temperature", settings.DEFAULT_TEMPERATURE, 0.0, 2.0),
        top_p=_number(body, "top_p", settings.DEFAULT_TOP_P, 0.0, 1.0),  # 0 keeps only the top token
        max_tokens=max_tokens,
        seed=seed,
        stop=stop,
        stream=bool(body.get("stream", False)),
        enable_thinking=enable_thinking,
    )


def split_thinking(text: str, thinking: bool) -> tuple[str, str | None]:
    """With thinking on, the template opens <think>; split the reply into (content, reasoning)."""
    if thinking and "</think>" in text:
        reasoning, content = text.split("</think>", 1)
        return content.lstrip("\n"), reasoning.strip()
    return text, None


def completion_body(model: str, content: str, reasoning: str | None, finish_reason: str,
                    prompt_tokens: int, completion_tokens: int, timing: dict) -> dict:
    """An OpenAI chat.completion object, plus an x_timing field clients may ignore."""
    message = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "system_fingerprint": f"{settings.BASE_MODEL_ID}@{settings.BASE_REVISION[:12]}",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason, "logprobs": None}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                  "total_tokens": prompt_tokens + completion_tokens},
        "x_timing": timing,
    }


def stream_chunks(body: dict) -> list[dict]:
    """Re-emit a finished completion as OpenAI stream chunks (one content chunk, then the finish).

    Generation is not incremental; this exists so clients that always stream still work.
    """
    choice = body["choices"][0]
    base = {"id": body["id"], "object": "chat.completion.chunk", "created": body["created"], "model": body["model"]}
    delta = {"role": "assistant", "content": choice["message"]["content"]}
    return [
        {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": choice["finish_reason"]}],
         "usage": body["usage"]},
    ]


def models_body(names: list[str], created: int) -> dict:
    """The /v1/models list object."""
    return {"object": "list",
            "data": [{"id": n, "object": "model", "created": created, "owned_by": "commissar"} for n in names]}
