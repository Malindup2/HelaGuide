"""
A small LLM client for the dialogue layer. The dialogue manager depends on the LLM protocol only.

OpenAICompatClient speaks the chat-completions format that Ollama, Groq, Gemini's OpenAI-compatible endpoint and
most gateways accept, so the provider is just C1_LLM_BASE_URL + C1_LLM_MODEL (same pattern as C2's client, own
code: components do not import each other). FakeLLM returns scripted replies, for tests: they never call a real LLM.

Every call returns the parsed JSON with its usage (tokens, model, latency): token cost per turn is an SO3 metric.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.settings import DialogueSettings

RETRY_STATUS = (429, 500, 502, 503, 504)
# short waits: a citizen is waiting for the reply, and a failed turn falls back to the rules path anyway
BACKOFF_SECONDS = (1.0, 3.0)
REPAIR_MESSAGE = "That was not valid JSON. Return only the JSON object, with no other text."
BODY_CHARS = 200        # response bodies in error messages are cut to this; headers are never included
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)
# a 400 that rejects JSON mode: the provider or model does not support response_format
_NO_JSON_MODE = re.compile(r"response_format|json[ _-]?mode|json_object", re.IGNORECASE)


class LLMError(RuntimeError):
    """The LLM could not be reached or did not return a JSON object."""


@dataclass
class LLMUsage:
    """Totals over every HTTP call one complete_json() made (a repair retry counts too)."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    latency_ms: float = 0.0
    calls: int = 0          # successful chat completions: 1, or 2 after a repair retry

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMResult:
    data: dict
    usage: LLMUsage = field(default_factory=LLMUsage)


class LLM(Protocol):
    def complete_json(self, system: str, messages: list[dict]) -> LLMResult: ...


def parse_json_object(text: str) -> dict:
    """The JSON object in a reply; tolerates a ```json fence around it. Raises ValueError otherwise."""
    m = _FENCE.match(text or "")
    data = json.loads(m.group(1) if m else text)
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object, got {type(data).__name__}")
    return data


class OpenAICompatClient:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 30.0, json_mode: bool = True,
                 attempts: int = len(BACKOFF_SECONDS) + 1, post=httpx.post, sleep=time.sleep) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        self.timeout = timeout
        self.json_mode = json_mode      # turned off for good after the provider rejects response_format
        self.attempts = max(1, attempts)
        self._post, self._sleep = post, sleep      # injectable for tests

    @classmethod
    def from_settings(cls, s: DialogueSettings) -> "OpenAICompatClient":
        return cls(s.base_url, s.model, s.api_key, s.timeout, s.json_mode)

    def complete_json(self, system: str, messages: list[dict]) -> LLMResult:
        """messages: [{"role": "user" | "assistant", "content": ...}], oldest first. One repair retry on bad JSON."""
        t0 = time.perf_counter()
        usage = LLMUsage(model=self.model)
        convo = [{"role": "system", "content": system}, *messages]
        text = self._chat(convo, usage)
        try:
            data = parse_json_object(text)
        except ValueError:
            text = self._chat(convo + [{"role": "assistant", "content": text},
                                       {"role": "user", "content": REPAIR_MESSAGE}], usage)
            try:
                data = parse_json_object(text)
            except ValueError as e:
                raise LLMError(f"LLM did not return a JSON object after a repair retry: {str(e)[:BODY_CHARS]}") \
                    from None
        usage.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        return LLMResult(data, usage)

    def _chat(self, messages: list[dict], usage: LLMUsage) -> str:
        """One chat completion (with retries); adds its token counts to `usage`. Returns the message text."""
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        last, attempt = "", 0
        while attempt < self.attempts:
            if attempt:
                self._sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
            attempt += 1
            body = {"model": self.model, "temperature": 0, "messages": messages}
            if self.json_mode:
                body["response_format"] = {"type": "json_object"}
            try:
                r = self._post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
            except httpx.TimeoutException as e:
                raise LLMError(f"LLM timed out after {self.timeout}s") from e   # a retry would double the wait
            except httpx.HTTPError as e:
                last = f"{type(e).__name__}: {str(e)[:BODY_CHARS]}"
                continue
            if r.status_code == 200:
                try:
                    data = r.json()
                    text = data["choices"][0]["message"]["content"] or ""
                except (ValueError, KeyError, IndexError, TypeError) as e:
                    raise LLMError(f"unexpected response shape: {e!r}"[:BODY_CHARS]) from None
                u = data.get("usage") or {}
                usage.prompt_tokens += int(u.get("prompt_tokens") or 0)
                usage.completion_tokens += int(u.get("completion_tokens") or 0)
                usage.model = data.get("model") or self.model
                usage.calls += 1
                return text
            last = f"HTTP {r.status_code}: {r.text[:BODY_CHARS]}"
            if r.status_code == 400 and "response_format" in body and _NO_JSON_MODE.search(r.text):
                # JSON mode not supported here: drop it for this and every later call, rely on prompt + parsing
                self.json_mode = False
                attempt -= 1        # this retry is free, and happens at most once per client
                continue
            if r.status_code not in RETRY_STATUS:
                break       # a bad key, model name or request will not get better by retrying
        raise LLMError(last)


class FakeLLM:
    """Scripted LLM for tests. Each call takes the next item: a dict is returned with fake usage, an LLMResult as
    is, an Exception is raised. `calls` records (system, messages) for assertions.
    Fake usage: prompt_tokens = words in system + messages, completion_tokens = words in the JSON reply."""

    def __init__(self, *replies, model="fake-llm", latency_ms=5.0):
        self.replies = list(replies)
        self.model, self.latency_ms = model, latency_ms
        self.calls: list[tuple[str, list[dict]]] = []

    def complete_json(self, system: str, messages: list[dict]) -> LLMResult:
        self.calls.append((system, [dict(m) for m in messages]))
        if not self.replies:
            raise LLMError("FakeLLM has no scripted reply left")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, LLMResult):
            return reply
        prompt = len(system.split()) + sum(len(str(m.get("content", "")).split()) for m in messages)
        completion = len(json.dumps(reply, ensure_ascii=False).split())
        return LLMResult(dict(reply), LLMUsage(prompt, completion, self.model, self.latency_ms, 1))
