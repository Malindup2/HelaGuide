"""
Demo: sends short conversations to a running C1 service (POST /v1/intent/details), one session each,
and prints one line per turn: text -> intent (confidence), route, slots, missing slots, language, latency.

    python scripts/demo_conversation.py                     # service at http://127.0.0.1:8001
    python scripts/demo_conversation.py --url http://127.0.0.1:8001 --only A B

Needs only the standard library. Start the service with STUB_MODE=false first (see ../README.md).
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid

# (session name, what it shows, [(user text, bot's last question or None), ...])
SESSIONS = [
    ("A", "NIC lost: memory, correction, orchestration", [
        ("mata ID eka nathi una, ikmanata aluth ekak one", None),
        ("Matara", "Koheda inne?"),
        ("ne ne, Galle", "Hari, Matara."),
    ]),
    ("B", "complaint: trust_verification", [
        ("oya kiwwa office eka saturday open kiyala, mama giyama wahala thibbe", None),
    ]),
    ("C", "unsupported service: fallback", [
        ("driving licence ekak ganna one", None),
    ]),
    ("SI", "Sinhala script: birth certificate copy", [
        ("මට දුවගේ උප්පැන්න සහතිකයේ පිටපතක් ඕනේ", None),
        ("ගාල්ලේ", "කොහෙද ලියාපදිංචි කළේ?"),
        ("පාසලට දාන්න", "මොකටද ඕනේ?"),
    ]),
    ("EN", "English: new passport, then a documents question", [
        ("I want to apply for a new passport", None),
        ("It's for my daughter", "Who is it for?"),
        ("We are travelling in mid December", "When are you travelling?"),
        ("what documents do I need?", None),
    ]),
]


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8001")
    ap.add_argument("--only", nargs="*", help="session names to run (default: all)")
    args = ap.parse_args()
    endpoint = args.url.rstrip("/") + "/v1/intent/details"
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")     # Sinhala in the Windows console

    for name, about, turns in SESSIONS:
        if args.only and name not in args.only:
            continue
        session_id = f"anon-demo-{name.lower()}-{uuid.uuid4().hex[:6]}"
        print(f"\n== {name}: {about}  ({session_id})")
        for text, bot_text in turns:
            try:
                d = post(endpoint, {"session_id": session_id, "text": text, "bot_text": bot_text})
            except urllib.error.HTTPError as e:
                sys.exit(f"{e.code} from {endpoint}: {e.read().decode('utf-8', 'replace')}")
            except urllib.error.URLError as e:
                sys.exit(f"cannot reach {endpoint}: {e.reason}. Is the service running?")
            if bot_text:
                print(f"   bot: {bot_text}")
            c = d["intent"]
            print(f"  user: {text}\n     -> {d['internal_intent']} ({d['confidence']:.2f}, {d['intent_source']})"
                  f"  route={d['route']}  slots={json.dumps(d['slots'], ensure_ascii=False)}"
                  f"  missing={d['missing_slots']}  lang={d['language']}  {d['latency_ms']:.0f} ms"
                  f"\n        contract: {c['intent']} {c['entities']['service_id']} district={c['entities']['district']}")


if __name__ == "__main__":
    main()
