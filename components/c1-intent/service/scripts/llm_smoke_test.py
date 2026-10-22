"""
Smoke test for the LLM dialogue layer against a real provider: sends turns 1-4 and 7 of the rigid demo log through
DialogueManager in hybrid mode with the current C1_LLM_* settings, and prints per turn the reply, intent, slots,
route, usage and latency, then whether JSON mode was kept or dropped. For a turn that fell back it prints the LLM
error message (already header-free and cut to 200 characters by the client). The API key is never printed.

Needs the real engine (pip install -e ".[research]" and the model folder, see ../README.md). Run from service/:

    set C1_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
    set C1_LLM_MODEL=gemini-3.8-flash
    set C1_LLM_REASONING_EFFORT=low
    set C1_LLM_API_KEY=...
    python scripts/llm_smoke_test.py > smoke_low.txt

Model names change and old ones are retired (a 404 from the endpoint): check the current list in Google AI Studio.
smoke_*.txt outputs are git-ignored. Exit code 1 when any turn fell back to the rules path.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # service/, for `app`

from app.core import pipeline                                   # noqa: E402
from app.core.dialogue import DialogueManager                   # noqa: E402
from app.core.llm_client import OpenAICompatClient              # noqa: E402
from app.core.settings import dialogue_settings                 # noqa: E402

# turns 1-4 and 7 of the rigid log (research/docs/c1_llm_dialogue_claude_code_prompt.md)
TURNS = ["I need a birth certifcate", "my mom", "kurunegala", "business reg purpose",
         "also i need to get a driving licese"]


class RecordingClient:
    """Wraps the client to keep the last error message for printing; the dialogue manager logs only its class."""

    def __init__(self, inner):
        self.inner = inner
        self.last_error = None

    def complete_json(self, system, messages):
        self.last_error = None
        try:
            return self.inner.complete_json(system, messages)
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            raise


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print each turn's full result as JSON")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")     # Sinhala in the Windows console

    settings = dialogue_settings()
    if settings.mode != "hybrid":
        settings = type(settings)(**{**vars(settings), "mode": "hybrid"})
    print(f"base url  {settings.base_url}")
    print(f"model     {settings.model}")
    print(f"reasoning effort {settings.reasoning_effort or 'not sent'}")
    print(f"api key   {'set' if settings.api_key else 'not set'}")
    print(f"json mode {'on' if settings.json_mode else 'off'} (C1_LLM_JSON_MODE)")
    print(f"timeout   {settings.timeout}s, history {settings.history_turns} turns\n")

    try:
        engine = pipeline.get_engine()
    except pipeline.EngineUnavailable as e:
        sys.exit(f"engine not available: {e}")
    client = OpenAICompatClient.from_settings(settings)
    recorder = RecordingClient(client)
    chat = DialogueManager(recorder, settings).new_session(engine.new_session())

    fallbacks = 0
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "provider_total_tokens": 0}
    for i, text in enumerate(TURNS):
        r = chat.step(text)
        u = r.llm_usage or {}
        for k in totals:
            totals[k] += u.get(k, 0)
        fallbacks += r.dialogue_source != "llm"
        print(f"[{i}] user    {text}")
        print(f"    reply   {r.reply}")
        print(f"    source  {r.dialogue_source}" + (f" ({r.error})" if r.error else "")
              + f" | act {r.dialogue_act} | intent {r.internal_intent} ({r.intent_source}; XLM-R "
              f"{r.intent_model_output} {r.confidence:.2f})")
        if r.dialogue_source != "llm" and recorder.last_error:
            print(f"    error   {recorder.last_error}")
        print(f"    state   active {r.active_intent} | tasks {r.tasks} | route {r.route} | ready {r.ready}")
        print(f"    slots   {r.slots}" + (f" raw {r.raw_slots}" if r.raw_slots else "")
              + f" | missing {r.missing_slots}")
        if r.conflicts or r.rejections:
            print(f"    checks  conflicts {[(c['slot'], c['kept']) for c in r.conflicts]} | rejected "
                  f"{[(x['field'], x['reason']) for x in r.rejections]}")
        p, c, total = u.get("prompt_tokens", 0), u.get("completion_tokens", 0), u.get("provider_total_tokens", 0)
        print(f"    usage   prompt {p} | completion {c} | reasoning {u.get('reasoning_tokens', 0)} | provider total "
              f"{total} (unexplained {total - p - c if total else '-'}) | calls {u.get('calls', 0)} | "
              f"model {u.get('model', '-')}")
        print(f"    latency {r.latency_ms} ms (nlu {r.nlu_ms}, llm {r.llm_ms})\n")
        if args.json:
            out = {k: v for k, v in vars(r).items() if k != "state"}
            print(json.dumps(out, ensure_ascii=False, indent=1))

    print(f"tokens    prompt {totals['prompt_tokens']} | completion {totals['completion_tokens']} | "
          f"reasoning {totals['reasoning_tokens']} | provider total {totals['provider_total_tokens']}")
    kept = "kept" if client.json_mode else ("dropped (provider rejected it)" if settings.json_mode else "off")
    print(f"json mode {kept}")
    print(f"fallbacks {fallbacks} of {len(TURNS)} turns")
    sys.exit(1 if fallbacks else 0)


if __name__ == "__main__":
    main()
