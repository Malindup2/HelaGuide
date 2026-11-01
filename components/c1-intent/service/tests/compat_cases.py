"""
Fixed requests for the /v1/intent and /v1/intent/details compatibility check (test_compat_context_v2.py).

compat_record.py runs them against the base branch (c1/context-v2) and saves the exact responses in
fixtures/compat_context_v2.json; the test replays them on this branch and compares the bytes. Same fake engine
(tests/conftest.py FakeEngine: scripted XLM-R, real Session and tracker) on both sides. Fictional data only.
"""
import re

# text -> (XLM-R intent, confidence); anything else gets FakeEngine's default (nic_replace_lost, 0.9)
INTENTS = {
    "I need a birth certificate": ("birth_cert_copy", 0.95),
    "my mom": ("birth_cert_copy", 0.95),
    "kurunegala": ("birth_cert_copy", 0.95),
    "business reg purpose": ("unsupported_service", 0.61),
    "school": ("birth_cert_copy", 0.52),
    "also i need to get a driving licese": ("birth_cert_copy", 0.72),
    "i need a driving license": ("birth_cert_copy", 0.33),
    "mata passport ekak ganna one": ("passport_new", 0.9),
    "normal": ("passport_new", 0.8),
    "mata ID eka nathi una": ("nic_replace_lost", 0.9),
    "Matara": ("nic_replace_lost", 0.9),
    "ne ne, Galle": ("nic_replace_lost", 0.9),
    "oya kiwwa office eka saturday open kiyala, mama giyama wahala thibbe": ("feedback_complaint", 0.9),
    "driving licence ekak ganna one": ("unsupported_service", 0.9),
    "මට දුවගේ උප්පැන්න සහතිකයේ පිටපතක් ඕනේ": ("birth_cert_copy", 0.93),
    "ගාල්ලේ": ("birth_cert_copy", 0.9),
    "පාසලට දාන්න": ("birth_cert_copy", 0.9),
    "I want to apply for a new passport": ("passport_new", 0.92),
    "It's for my daughter": ("passport_new", 0.88),
    "We are travelling in mid December": ("passport_new", 0.9),
    "what documents do I need?": ("general_question", 0.85),
    "i need a NIC": ("nic_new", 0.7),
    "aluth ekak": ("nic_new", 0.8),
    "danne na": ("nic_new", 0.4),
    "what is the weather today": ("out_of_scope", 0.9),
    "hmm": ("out_of_scope", 0.2),
}

D, I = "/v1/intent/details", "/v1/intent"
# (path, body). Sessions mix both endpoints, as the gateway and the demo do.
REQUESTS = [
    # the rigid log, through /details with the engine's own replies as bot_text, as the demo page does
    (D, {"session_id": "anon-rigid", "text": "Hi"}),
    (D, {"session_id": "anon-rigid", "text": "I need a birth certificate", "bot_text": None}),
    (D, {"session_id": "anon-rigid", "text": "my mom", "bot_text": "Who is it for?"}),
    (D, {"session_id": "anon-rigid", "text": "kurunegala", "bot_text": "Which district are you in?"}),
    (D, {"session_id": "anon-rigid", "text": "business reg purpose", "bot_text": "What is the purpose?"}),
    (I, {"session_id": "anon-rigid", "text": "school"}),
    (D, {"session_id": "anon-rigid", "text": "also i need to get a driving licese"}),
    (I, {"session_id": "anon-rigid", "text": "i need a driving license"}),
    # passport through the contract endpoint only
    (I, {"session_id": "anon-pp", "text": "mata passport ekak ganna one"}),
    (I, {"session_id": "anon-pp", "text": "normal"}),
    # lost NIC with a correction, mixed endpoints
    (D, {"session_id": "anon-nic", "text": "mata ID eka nathi una"}),
    (D, {"session_id": "anon-nic", "text": "Matara", "bot_text": "Koheda inne?"}),
    (I, {"session_id": "anon-nic", "text": "ne ne, Galle"}),
    # complaint, unsupported service, out of scope, low confidence
    (D, {"session_id": "anon-cmp", "text": "oya kiwwa office eka saturday open kiyala, mama giyama wahala thibbe"}),
    (I, {"session_id": "anon-uns", "text": "driving licence ekak ganna one"}),
    (D, {"session_id": "anon-oos", "text": "what is the weather today"}),
    (D, {"session_id": "anon-low", "text": "hmm"}),
    # Sinhala script
    (D, {"session_id": "anon-si", "text": "මට දුවගේ උප්පැන්න සහතිකයේ පිටපතක් ඕනේ"}),
    (D, {"session_id": "anon-si", "text": "ගාල්ලේ", "bot_text": "කොහෙද ලියාපදිංචි කළේ?"}),
    (D, {"session_id": "anon-si", "text": "පාසලට දාන්න", "bot_text": "මොකටද ඕනේ?"}),
    # English passport, then a documents question (contract intent check_requirements)
    (D, {"session_id": "anon-en", "text": "I want to apply for a new passport"}),
    (D, {"session_id": "anon-en", "text": "It's for my daughter", "bot_text": "Who is it for?"}),
    (D, {"session_id": "anon-en", "text": "We are travelling in mid December", "bot_text": "When are you travelling?"}),
    (I, {"session_id": "anon-en", "text": "what documents do I need?"}),
    # NIC without a variant, the variant answer, and "danne na"
    (D, {"session_id": "anon-var", "text": "i need a NIC"}),
    (D, {"session_id": "anon-var", "text": "aluth ekak",
         "bot_text": "Aluth NIC ekak da, wenas karanna da, nathi una ekak da?"}),
    (D, {"session_id": "anon-var", "text": "danne na", "bot_text": "Meka kaageda?"}),
    # validation errors
    (I, {"session_id": "anon-bad", "text": ""}),
    (I, {"session_id": "anon-bad", "text": "hi", "user_name": "x"}),
    (D, {"session_id": "anon-bad", "text": "hi", "bot_text": "x" * 2001}),
    (D, {"text": "hi"}),
]

_LATENCY = re.compile(r'"latency_ms":\s*[0-9.eE+-]+')


def normalise(body: str) -> str:
    """The response text with latency_ms (wall-clock time, never the same twice) set to 0. Nothing else changes."""
    return _LATENCY.sub('"latency_ms":0', body)


def install_fake_engine(pipeline, session_store_cls, fake_engine_cls, model_dir, setattr_, setenv, delenv):
    """Real mode with the fake engine and empty session stores: the same as conftest's real_mode fixture.
    setattr_ / setenv / delenv: monkeypatch's in the test, plain ones in compat_record.py."""
    (model_dir / "c1_config.json").write_text("{}", encoding="utf-8")
    setenv("STUB_MODE", "false")
    setenv("C1_MODEL_DIR", str(model_dir))
    delenv("C1_MIN_CONFIDENCE")
    setattr_(pipeline, "_engine", None)
    setattr_(pipeline, "_store", session_store_cls())
    setattr_(pipeline, "_load_engine", lambda path: fake_engine_cls(
        dict(INTENTS), pipeline.min_confidence(), pipeline.unsupported_service_fallback))


def run(client):
    """-> [{"path", "request", "status", "body"}] with the normalised response text."""
    out = []
    for path, body in REQUESTS:
        r = client.post(path, json=body)
        out.append({"path": path, "request": body, "status": r.status_code, "body": normalise(r.text)})
    return out


def run_stub(client):
    """The same two endpoints in stub mode (STUB_MODE=true), one request each."""
    out = []
    for path in (I, D):
        r = client.post(path, json={"session_id": "anon-stub", "text": "mata passport ekak ganna one"})
        out.append({"path": path, "status": r.status_code, "body": normalise(r.text)})
    return out


def contract_openapi(app):
    """The OpenAPI paths of /v1/intent and /v1/intent/details and every schema they reference."""
    spec = app.openapi()
    paths = {p: spec["paths"][p] for p in (I, D)}
    schemas, todo = {}, [paths]
    while todo:
        node = todo.pop()
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[1]
                if name not in schemas:
                    schemas[name] = spec["components"]["schemas"][name]
                    todo.append(schemas[name])
            todo.extend(node.values())
        elif isinstance(node, list):
            todo.extend(node)
    return {"paths": paths, "schemas": dict(sorted(schemas.items()))}
