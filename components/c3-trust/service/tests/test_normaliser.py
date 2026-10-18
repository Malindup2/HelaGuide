import json

import httpx
import pytest

from app.core.normaliser import (GeminiClient, Normaliser, QuotaExhausted, RateLimited, TranslationError,
                                 numbers_preserved, parse_rate_limit)
from app.core.util import text_hash
from tests.helpers import make_settings


def _gemini_ok(text_en):
    body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"text_en": text_en})}]}}]}
    return httpx.Response(200, json=body)


def _client(handler, key="test-key"):
    return GeminiClient(key, "gemini-test", client=httpx.Client(transport=httpx.MockTransport(handler)), pause=0)


@pytest.fixture
def norm(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({text_hash("passport eke fee eka 12000"): {"text_en": "The passport fee is 12000", "source": "authored"}}))
    return Normaliser(make_settings(), cache_path=cache)


def test_supplied_english_wins(norm):
    r = norm.normalise("anything", "mixed", "Already English")
    assert (r.text_en, r.backend) == ("Already English", "supplied")


def test_english_needs_no_translation(norm):
    r = norm.normalise("The fee was 12,000", "en")
    assert r.text_en == "The fee was 12,000" and r.backend == "not_needed"


def test_language_is_detected_when_missing(norm):
    assert norm.normalise("The fee was 12,000", None).backend == "not_needed"
    assert norm.normalise("passport eke fee eka 12000", None).backend == "cache"


def test_cache_hit(norm):
    r = norm.normalise("passport eke fee eka 12000", "mixed")
    assert r.text_en == "The passport fee is 12000" and r.backend == "cache"


def test_miss_with_live_off_is_unavailable_not_a_crash(norm):
    r = norm.normalise("passport eke fee eka 99999", "mixed")
    assert r.text_en is None and r.backend == "unavailable"


def test_live_translation_is_used_when_allowed_and_cached(tmp_path):
    n = Normaliser(make_settings(allow_live_llm=True, gemini_api_key="k"), cache_path=tmp_path / "c.json",
                   client=_client(lambda req: _gemini_ok("They charged 4000.")))
    r = n.normalise("fee eka 4000k gaththa", "mixed")
    assert r.text_en == "They charged 4000." and r.backend == "gemini_live"
    assert n.normalise("fee eka 4000k gaththa", "mixed").backend == "cache"


def test_translation_that_changes_a_number_is_rejected():
    c = _client(lambda req: _gemini_ok("They charged 5000."))
    with pytest.raises(TranslationError, match="numbers changed"):
        c.translate("fee eka 4000k gaththa")
    assert numbers_preserved("fee 12,000", "the fee is 12000") and not numbers_preserved("fee 12000", "the fee changed")


def test_retries_then_succeeds_on_rate_limit():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429) if len(calls) < 3 else _gemini_ok("It cost 300.")

    assert _client(handler).translate("fee 300") == "It cost 300."
    assert len(calls) == 3


def test_gives_up_cleanly():
    with pytest.raises(TranslationError, match="gave up"):
        _client(lambda req: httpx.Response(503)).translate("fee 300", retries=2)


def test_missing_key_and_bad_responses():
    with pytest.raises(TranslationError, match="no Gemini API key"):
        _client(lambda req: _gemini_ok("x"), key="").translate("fee 300")
    with pytest.raises(TranslationError, match="HTTP 400"):
        _client(lambda req: httpx.Response(400, text="bad model")).translate("fee 300")
    with pytest.raises(TranslationError, match="unexpected response"):
        _client(lambda req: httpx.Response(200, json={"candidates": []})).translate("fee 300")


def test_the_api_key_goes_in_a_header_not_the_url():
    seen = {}

    def handler(req):
        seen["header"] = req.headers.get("x-goog-api-key")
        seen["url"] = str(req.url)
        return _gemini_ok("It cost 300.")

    _client(handler, key="SECRET").translate("fee 300")
    assert seen["header"] == "SECRET" and "SECRET" not in seen["url"]


def test_list_models_keeps_only_generate_capable_models():
    body = {"models": [{"name": "models/a", "supportedGenerationMethods": ["generateContent"]},
                       {"name": "models/b", "supportedGenerationMethods": ["embedContent"]}]}
    assert _client(lambda req: httpx.Response(200, json=body)).list_models() == ["a"]


def test_every_saved_translation_keeps_every_number():
    path = make_settings().data_dir / "normalised_cache.json"
    for e in json.loads(path.read_text(encoding="utf-8")).values():
        assert numbers_preserved(e["raw_text"], e["text_en"]), e


# --------------------------------------------------- Google's own "retry in N seconds"
def _limited(delay="12s", quota="GenerateRequestsPerMinutePerProjectPerModel-FreeTier"):
    body = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": quota}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}]}}
    return httpx.Response(429, json=body)


def test_parse_rate_limit_reads_googles_delay_and_the_per_day_flag():
    assert parse_rate_limit(_limited("34s")) == (34.0, False)
    assert parse_rate_limit(_limited("7.5s")) == (7.5, False)
    assert parse_rate_limit(_limited("3s", "GenerateRequestsPerDayPerProjectPerModel-FreeTier")) == (3.0, True)
    assert parse_rate_limit(httpx.Response(429, headers={"retry-after": "20"})) == (20.0, False)
    assert parse_rate_limit(httpx.Response(429, text="not json")) == (None, False)


def test_a_429_waits_as_long_as_google_asks_then_succeeds():
    calls, slept = [], []

    def handler(req):
        calls.append(1)
        return _limited("12s") if len(calls) == 1 else _gemini_ok("It cost 300.")

    c = GeminiClient("k", "m", client=httpx.Client(transport=httpx.MockTransport(handler)), pause=1, sleep=slept.append)
    assert c.translate("fee 300") == "It cost 300."
    assert slept == [13.0]                       # Google's 12 s plus one second of margin


def test_repeated_429_becomes_a_clear_rate_limited_error_with_the_wait_time():
    c = GeminiClient("k", "m", client=httpx.Client(transport=httpx.MockTransport(lambda r: _limited("20s"))),
                     pause=1, sleep=lambda s: None)
    with pytest.raises(RateLimited) as e:
        c.translate("fee 300", retries=3)
    assert e.value.retry_after == 20.0 and "too many requests" in str(e.value)


def test_the_daily_quota_stops_immediately_without_retrying():
    calls = []

    def handler(req):
        calls.append(1)
        return _limited("5s", "GenerateRequestsPerDayPerProjectPerModel-FreeTier")

    c = GeminiClient("k", "m", client=httpx.Client(transport=httpx.MockTransport(handler)), pause=1, sleep=lambda s: None)
    with pytest.raises(QuotaExhausted, match="DAILY"):
        c.translate("fee 300")
    assert len(calls) == 1                       # no pointless retries that would burn more quota
