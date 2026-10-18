"""
normalise(): turn a citizen's message into plain English so one grounding procedure can
handle English, Sinhala script and Singlish.

Order of attempts (the demo needs no key and no internet):
  1. English text supplied by C1 (text_en)           -> backend "supplied"
  2. the message is already English                    -> backend "not_needed"
  3. a saved translation in the cache file             -> backend "cache"
  4. a live Gemini call (only if C3_ALLOW_LIVE_LLM)    -> backend "gemini_live"
  5. nothing worked                                    -> text_en is None, grounding asks a question

Safety check: every number written with digits in the original must appear in the
translation, so a fee can never be silently changed by the translator.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.config import C3Settings
from app.core.lexicon import detect_language, needs_translation
from app.core.util import numbers_in, text_hash

log = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"

PROMPT = """You translate short citizen feedback about Sri Lankan government services into plain English.
The message may be in Sinhala script, in romanised Sinhala ("Singlish"), in English, or a mixture.

Rules:
- Keep every number exactly as written with digits.
- Keep acronyms and proper nouns unchanged (NIC, Grama Niladhari, Immigration, Registrar General).
- Keep the meaning exactly, including negations ("not", "did not").
- Do not add facts, advice or explanations.
- Use one or two short, plain sentences.

Return ONLY JSON in this form: {{"text_en": "<the English translation>"}}

Message: <<<{raw}>>>"""


class TranslationError(RuntimeError):
    pass


class RateLimited(TranslationError):
    """Google says: too many requests this minute. `retry_after` is Google's own suggested wait (seconds)."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class QuotaExhausted(TranslationError):
    """The DAILY free quota is used up. Retrying today is pointless; the quota resets at midnight Pacific time."""


def parse_rate_limit(resp: httpx.Response) -> tuple[float | None, bool]:
    """From a 429 answer: (seconds Google asks us to wait, is it the per-DAY limit?)."""
    delay: float | None = None
    per_day = False
    header = resp.headers.get("retry-after")
    if header:
        try:
            delay = float(header)
        except ValueError:
            pass
    try:
        for d in resp.json().get("error", {}).get("details", []):
            if "retryDelay" in d:
                try:
                    delay = float(str(d["retryDelay"]).rstrip("s"))
                except ValueError:
                    pass
            for v in d.get("violations", []):
                if "perday" in str(v.get("quotaId", "")).lower():
                    per_day = True
    except Exception:
        pass
    return delay, per_day


@dataclass
class NormResult:
    text_en: str | None
    backend: str
    language: str
    note: str | None = None


def numbers_preserved(raw: str, translated: str) -> bool:
    want = set(numbers_in(raw))
    have = set(numbers_in(translated))
    return want <= have


class GeminiClient:
    def __init__(self, api_key: str, model: str, client: httpx.Client | None = None, pause: float = 4.0,
                 sleep=time.sleep):
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=httpx.Timeout(30.0))
        self.pause = pause          # 0 = never wait (tests)
        self._sleep = sleep

    def _headers(self) -> dict:
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def translate(self, raw_text: str, retries: int = 3) -> str:
        if not self.api_key:
            raise TranslationError("no Gemini API key (set C3_GEMINI_API_KEY in service/.env)")
        body = {
            "contents": [{"parts": [{"text": PROMPT.format(raw=raw_text)}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        url = f"{GEMINI_URL}/{self.model}:generateContent"
        last = "unknown error"
        retry_after: float | None = None
        for attempt in range(retries):
            try:
                r = self.client.post(url, headers=self._headers(), json=body)
            except httpx.HTTPError as exc:
                last = f"network error: {type(exc).__name__}"
                if self.pause and attempt < retries - 1:
                    self._sleep(min(2 ** attempt, 8))
                continue
            if r.status_code == 429:
                delay, per_day = parse_rate_limit(r)
                if per_day:
                    raise QuotaExhausted("the DAILY free quota of this Gemini model is used up "
                                         "(it resets at midnight Pacific time; try again tomorrow or use another model)")
                last, retry_after = "HTTP 429", delay
                if attempt < retries - 1 and self.pause:
                    # wait as long as Google asks (capped), otherwise back off
                    self._sleep(min(delay + 1.0, 90.0) if delay else min(2 ** attempt * 5, 30))
                continue
            if r.status_code in (500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                if attempt < retries - 1 and self.pause:
                    self._sleep(min(2 ** attempt * 2, 20))
                continue
            if r.status_code != 200:
                raise TranslationError(f"HTTP {r.status_code}: {r.text[:300]}")
            return self._parse(r.json(), raw_text)
        if last == "HTTP 429":
            raise RateLimited(f"gave up after {retries} tries (HTTP 429: too many requests this minute)", retry_after)
        raise TranslationError(f"gave up after {retries} tries ({last})")

    @staticmethod
    def _parse(data: dict, raw_text: str) -> str:
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TranslationError(f"unexpected response shape: {str(data)[:300]}") from exc
        text = text.strip()
        try:
            out = json.loads(text)["text_en"]
        except (ValueError, KeyError, TypeError):
            m = re.search(r'"text_en"\s*:\s*"(.+?)"\s*}', text, re.S)
            if not m:
                raise TranslationError(f"could not read JSON from: {text[:200]}")
            out = m.group(1)
        out = str(out).strip()
        if not out:
            raise TranslationError("empty translation")
        if not numbers_preserved(raw_text, out):
            raise TranslationError(f"numbers changed: {raw_text!r} -> {out!r}")
        return out

    def list_models(self) -> list[str]:
        r = self.client.get(GEMINI_URL, headers=self._headers(), params={"pageSize": 200})
        if r.status_code != 200:
            raise TranslationError(f"HTTP {r.status_code}: {r.text[:300]}")
        names = []
        for m in r.json().get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                names.append(m["name"].removeprefix("models/"))
        return names


class Normaliser:
    def __init__(self, settings: C3Settings, cache_path: Path | None = None,
                 client: GeminiClient | None = None):
        self.settings = settings
        self.cache_path = cache_path or (settings.data_dir / "normalised_cache.json")
        self.cache: dict[str, dict] = {}
        self._load()
        self._client = client

    # ---- cache -------------------------------------------------------------
    def _load(self) -> None:
        if self.cache_path.exists():
            self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2, sort_keys=True),
                                   encoding="utf-8")

    def put(self, raw_text: str, text_en: str, source: str, model: str | None = None, reviewed: bool = False) -> None:
        self.cache[text_hash(raw_text)] = {
            "raw_text": raw_text.strip(), "text_en": text_en, "source": source, "model": model,
            "reviewed": reviewed, "created_at": datetime.now(timezone.utc).isoformat()}

    def client(self) -> GeminiClient:
        if self._client is None:
            self._client = GeminiClient(self.settings.gemini_api_key, self.settings.gemini_model,
                                        pause=self.settings.llm_pause_seconds)
        return self._client

    # ---- main entry --------------------------------------------------------------
    def normalise(self, raw_text: str, language: str | None = None, supplied_en: str | None = None) -> NormResult:
        lang = language or detect_language(raw_text)
        if supplied_en:
            return NormResult(supplied_en.strip(), "supplied", lang)
        if not needs_translation(lang, raw_text):
            return NormResult(raw_text.strip(), "not_needed", lang)
        hit = self.cache.get(text_hash(raw_text))
        if hit:
            return NormResult(hit["text_en"], "cache", lang, note=f"source={hit.get('source')}")
        if self.settings.allow_live_llm:
            try:
                out = self.client().translate(raw_text)
            except TranslationError as exc:
                log.warning("live translation failed: %s", exc)
                return NormResult(None, "unavailable", lang, note=str(exc))
            self.put(raw_text, out, "gemini_live", self.settings.gemini_model)
            return NormResult(out, "gemini_live", lang)
        return NormResult(None, "unavailable", lang, note="not in cache and live translation is off")
