"""
A small LLM client for the dialogue layer. The dialogue manager depends on the LLM protocol only.

OpenAICompatClient speaks the chat-completions format that Ollama, Groq, Gemini's OpenAI-compatible endpoint and
most gateways accept, so the provider is just C1_LLM_BASE_URL + C1_LLM_MODEL (same pattern as C2's client, own
code: components do not import each other). FakeLLM returns scripted replies, for tests: they never call a real LLM.

Every call returns the parsed JSON with its usage (tokens, model, latency): token cost per turn is an SO3 metric.
Reasoning ("thinking") tokens are recorded separately when the provider reports them. Providers differ on whether
completion_tokens already includes them (OpenAI-style APIs do), so they are not added to total_tokens.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.settings import DialogueSettings

# Retries are short: a citizen is waiting for the reply, and a failed turn falls back to the rules path anyway.
#   429 "quota exceeded"      no retry (a retry only burns more quota)
#   other 429 (rate limit)    one retry, after the provider's retry delay (Retry-After / retryDelay), at most 5 s
#   5xx, transport errors     one retry after 1 s
#   timeout, refused connect  no retry (see _chat)
ATTEMPTS = 2
RETRY_WAIT = 1.0
MAX_RETRY_WAIT = 5.0
SERVER_ERRORS = (500, 502, 503, 504)
_QUOTA_EXCEEDED = re.compile(r"exceeded (?:your )?(?:current )?quota|quota (?:has been )?exceeded", re.IGNORECASE)
_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')     # Gemini: error.details[].retryDelay
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
    reasoning_tokens: int = 0       # thinking tokens, when reported (completion_tokens_details.reasoning_tokens)
    model: str = ""
    latency_ms: float = 0.0
    calls: int = 0          # successful chat completions: 1, or 2 after a repair retry
    # usage.total_tokens as the provider reports it (0 if absent). More than prompt + completion means tokens the
    # other fields do not show, e.g. thinking that a provider bills but does not report as reasoning_tokens
    provider_total_tokens: int = 0

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
                 reasoning_effort: str = "", attempts: int = ATTEMPTS, post=httpx.post,
                 sleep=time.sleep) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        self.timeout = timeout
        self.json_mode = json_mode      # turned off for good after the provider rejects response_format
        self.reasoning_effort = reasoning_effort    # "" = not sent
        self.attempts = max(1, attempts)
        self._post, self._sleep = post, sleep      # injectable for tests

    @classmethod
    def from_settings(cls, s: DialogueSettings) -> "OpenAICompatClient":
        return cls(s.base_url, s.model, s.api_key, s.timeout, s.json_mode, s.reasoning_effort)

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
        last, attempt, wait = "", 0, 0.0
        while attempt < self.attempts:
            if wait:
                self._sleep(wait)
            attempt += 1
            wait = RETRY_WAIT
            body = {"model": self.model, "temperature": 0, "messages": messages}
            if self.json_mode:
                body["response_format"] = {"type": "json_object"}
            if self.reasoning_effort:
                body["reasoning_effort"] = self.reasoning_effort
            try:
                r = self._post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
            except httpx.TimeoutException as e:
                raise LLMError(f"LLM timed out after {self.timeout}s") from e   # a retry would double the wait
            except httpx.ConnectError as e:
                # nothing is listening (Ollama not started, wrong URL): a retry only delays the rules fallback
                raise LLMError(f"ConnectError: {str(e)[:BODY_CHARS]}") from e
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
                usage.reasoning_tokens += _reasoning_tokens(u)
                usage.provider_total_tokens += int(u.get("total_tokens") or 0)
                usage.model = data.get("model") or self.model
                usage.calls += 1
                return text
            last = f"HTTP {r.status_code}: {r.text[:BODY_CHARS]}"
            if r.status_code == 400 and "response_format" in body and _NO_JSON_MODE.search(r.text):
                # JSON mode not supported here: drop it for this and every later call, rely on prompt + parsing
                self.json_mode = False
                attempt, wait = attempt - 1, 0.0    # this retry is free and immediate, at most once per client
                continue
            if r.status_code == 429:
                if _QUOTA_EXCEEDED.search(r.text):
                    break       # quota used up: retrying only burns more of it
                wait = retry_delay(r)
                continue
            if r.status_code not in SERVER_ERRORS:
                break       # a bad key, model name or request will not get better by retrying
        raise LLMError(last)


def retry_delay(r: httpx.Response) -> float:
    """Seconds to wait before retrying a 429: the Retry-After header or Gemini's retryDelay, capped at
    MAX_RETRY_WAIT; RETRY_WAIT when the provider gives none."""
    raw = r.headers.get("retry-after")
    m = None if raw else _RETRY_DELAY.search(r.text)
    try:
        seconds = float(raw if raw else m.group(1)) if (raw or m) else RETRY_WAIT
    except ValueError:      # Retry-After can also be an HTTP date: not worth parsing here
        seconds = RETRY_WAIT
    return min(max(seconds, 0.0), MAX_RETRY_WAIT)


def _reasoning_tokens(u: dict) -> int:
    """completion_tokens_details.reasoning_tokens (OpenAI style), or a top-level reasoning_tokens."""
    details = u.get("completion_tokens_details")
    value = details.get("reasoning_tokens") if isinstance(details, dict) else None
    try:
        return int(value or u.get("reasoning_tokens") or 0)
    except (TypeError, ValueError):
        return 0


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
        return LLMResult(dict(reply), LLMUsage(prompt, completion, 0, self.model, self.latency_ms, 1))
