"""A minimal language-model client. The extractor depends on the LLM protocol only.

OpenAICompatClient speaks the chat-completions format that OpenAI, Groq, Ollama and most
gateways accept, so one class covers the provider choice: set the base URL and model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass
class LLMReply:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""


class LLM(Protocol):
    def complete(self, system: str, user: str) -> LLMReply: ...


# Waits between attempts. A "high demand" 503 from a provider lasts seconds to minutes.
BACKOFF_SECONDS = (5, 15, 40, 60)


class LLMError(RuntimeError):
    pass


class OpenAICompatClient:
    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1",
                 timeout: float = 120.0, retries: int = 4,
                 reasoning_effort: str | None = None) -> None:
        self.api_key, self.model = api_key, model
        self.reasoning_effort = reasoning_effort
        self.base_url = base_url.rstrip("/")
        self.timeout, self.retries = timeout, retries

    def complete(self, system: str, user: str) -> LLMReply:
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self.reasoning_effort:  # "none", "low", "medium" or "high", where the provider has it
            body["reasoning_effort"] = self.reasoning_effort
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last = ""
        for attempt in range(self.retries):
            try:
                r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers,
                               timeout=self.timeout)
            except httpx.HTTPError as e:
                last = f"{type(e).__name__}: {e}"
            else:
                if r.status_code == 200:
                    data = r.json()
                    usage = data.get("usage") or {}
                    return LLMReply(
                        text=data["choices"][0]["message"]["content"] or "",
                        prompt_tokens=int(usage.get("prompt_tokens", 0)),
                        completion_tokens=int(usage.get("completion_tokens", 0)),
                        model=data.get("model", self.model),
                    )
                last = f"HTTP {r.status_code}: {r.text[:200]}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    break  # a bad key or bad request will not get better by retrying
            time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
        raise LLMError(last)
