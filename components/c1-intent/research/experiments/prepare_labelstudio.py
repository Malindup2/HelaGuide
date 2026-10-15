r"""
Merge seed dialogues and build a Label Studio import file with pre-annotations.

Run from the project folder:
    conda activate nlp
    python src\prepare_labelstudio.py

Inputs : data/seed_dialogues_*.json
Outputs: data/seed_all.json   (all dialogues merged, code_mix filled in)
         data/ls_tasks.json   (one task per user turn, with guessed labels to correct)
"""
import glob
import json
import re
import uuid
from pathlib import Path

DATA = Path("data")

# ---------------------------------------------------------------- word lists
# Romanized words that are English. Anything romanized and NOT here is guessed SI.
# Note: "one" is deliberately missing: in Singlish it usually means ඕනේ (need).
EN_WORDS = {
    "nic", "id", "address", "change", "update", "passport", "certificate", "birth",
    "copy", "license", "licence", "renew", "expire", "expires", "school", "admission",
    "police", "clearance", "report", "bank", "account", "open", "business", "register",
    "small", "partnership", "company", "private", "limited", "building", "permit",
    "water", "line", "pipe", "current", "connection", "office", "fee", "documents",
    "document", "photo", "travel", "day", "service", "normal", "urgent", "first",
    "time", "car", "bike", "heavy", "vehicle", "lorry", "online", "visa", "job",
    "abroad", "hospital", "town", "road", "temple", "lake", "wedding", "marriage",
    "death", "mid", "december", "january", "next", "week", "month", "sorry", "hello",
    "wait", "match", "list", "i", "need", "a", "for", "my", "how", "long", "does", "it",
    "take", "can", "in", "the", "what", "do", "to", "is", "of", "when", "are", "you",
    "your", "usually", "few", "weeks", "gn", "ds", "dmt", "flight", "mid", "district",
}

PLACES = {
    # romanized
    "colombo", "galle", "kandy", "matale", "gampaha", "kalutara", "kurunegala",
    "wariyapola", "negombo", "jaffna", "kadawatha", "maharagama", "hambantota",
    "batticaloa", "dambulla", "moratuwa", "chilaw", "puttalam", "panadura", "badulla",
    "monaragala", "ratnapura", "kegalle", "polonnaruwa", "anuradhapura", "matara",
    "nuwara", "eliya", "nugegoda", "hikkaduwa", "homagama", "kaduwela", "tangalle",
    "canada", "australia", "sri", "lanka",
    # Sinhala script
    "කොළඹ", "ගාල්ල", "මහනුවර", "මාතලේ", "ගම්පහ", "කළුතර", "කුරුණෑගල", "අනුරාධපුර",
    "මාතර", "රත්නපුර", "නුවරඑළිය", "කෑගල්ල", "හම්බන්තොට", "තංගල්ල", "හෝමාගම",
    "කඩුවෙල", "හික්කඩුව", "මහරගම", "නුගේගොඩ", "පානදුර",
}

# District values are stored in English; this lets us find them in Sinhala-script text.
DISTRICT_SI = {
    "Colombo": "කොළඹ", "Galle": "ගාල්ල", "Kandy": "මහනුවර", "Matale": "මාතලේ",
    "Gampaha": "ගම්පහ", "Kalutara": "කළුතර", "Kurunegala": "කුරුණෑගල",
    "Anuradhapura": "අනුරාධපුර", "Matara": "මාතර", "Ratnapura": "රත්නපුර",
    "Nuwara Eliya": "නුවරඑළිය", "Kegalle": "කෑගල්ල", "Hambantota": "හම්බන්තොට",
}
ADDRESS_SI = {
    "Tangalle": "තංගල්ල", "Homagama": "හෝමාගම", "Kaduwela": "කඩුවෙල",
    "Hikkaduwa": "හික්කඩුව", "Maharagama": "මහරගම", "Nugegoda": "නුගේගොඩ",
}

SINHALA_CHARS = re.compile(r"[\u0D80-\u0DFF]")

# Only these slots are spans in the text. Enum slots (applicant_for, urgency, ...)
# are classified at turn level, so they are NOT highlighted.
EXTRACTIVE_SLOTS = {"district", "address", "new_value", "date", "travel_date",
                    "date_of_birth", "purpose", "vehicle_class", "service_mentioned", "issue"}
TRIM = ".,?!…;:\"'()"


def guess_lang(word: str) -> str:
    w = word.lower()
    if w in PLACES or word in PLACES:
        return "NE"
    if SINHALA_CHARS.search(word):
        return "SI"
    if re.fullmatch(r"[\d/]+", word):
        return "OTHER"
    if re.search(r"\d", word) and re.search(r"[a-zA-Z]", word):
        return "MIXED"  # e.g. "16i" = number + Sinhala suffix
    if w in EN_WORDS:
        return "EN"
    return "SI"  # romanized, not a known English word -> probably Singlish


def words_with_offsets(text: str):
    for m in re.finditer(r"\S+", text):
        raw, start = m.group(), m.start()
        lead = len(raw) - len(raw.lstrip(TRIM))
        word = raw.strip(TRIM)
        if word:
            yield word, start + lead, start + lead + len(word)


def rid() -> str:
    return uuid.uuid4().hex[:10]


def slot_spans(text: str, slots: dict):
    """Find extractive slot values (text that literally appears in the turn)."""
    results = []
    lower = text.lower()
    for slot, value in slots.items():
        if slot not in EXTRACTIVE_SLOTS or not isinstance(value, str):
            continue
        candidates = [value]
        if slot == "district" and value in DISTRICT_SI:
            candidates.append(DISTRICT_SI[value])
        if slot == "address" and value in ADDRESS_SI:
            candidates.append(ADDRESS_SI[value])
        for cand in candidates:
            i = lower.find(cand.lower())
            if i != -1:
                results.append({
                    "id": rid(), "from_name": "slot", "to_name": "text", "type": "labels",
                    "value": {"start": i, "end": i + len(cand), "text": text[i:i + len(cand)],
                              "labels": [slot]},
                })
                break
    return results


def main():
    files = sorted(glob.glob(str(DATA / "seed_dialogues_*.json")))
    dialogues = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            dialogues.extend(json.load(fh))
    for d in dialogues:
        d.setdefault("code_mix", "mixed")

    with open(DATA / "seed_all.json", "w", encoding="utf-8") as fh:
        json.dump(dialogues, fh, ensure_ascii=False, indent=2)

    tasks = []
    for d in dialogues:
        prev_bot = ""
        for i, t in enumerate(d["turns"]):
            if t["speaker"] == "bot":
                prev_bot = t["text"]
                continue
            text = t["text"]
            state = t.get("state", {})
            lang = [{
                "id": rid(), "from_name": "lang", "to_name": "text", "type": "labels",
                "value": {"start": s, "end": e, "text": w, "labels": [guess_lang(w)]},
            } for w, s, e in words_with_offsets(text)]
            tasks.append({
                "data": {
                    "text": text,
                    "context": f"Bot asked: {prev_bot}" if prev_bot else "(first turn)",
                    "info": f"{d['dialogue_id']} | turn {i} | intent: {state.get('intent')} | {d['code_mix']}",
                    "dialogue_id": d["dialogue_id"],
                    "turn": i,
                    "intent": state.get("intent"),
                    "code_mix": d["code_mix"],
                },
                "predictions": [{
                    "model_version": "heuristic_v0",
                    "result": lang + slot_spans(text, state.get("slots", {})),
                }],
            })

    with open(DATA / "ls_tasks.json", "w", encoding="utf-8") as fh:
        json.dump(tasks, fh, ensure_ascii=False, indent=2)
    print(f"Merged {len(dialogues)} dialogues from {len(files)} files -> data/seed_all.json")
    print(f"Wrote {len(tasks)} labelling tasks (user turns) -> data/ls_tasks.json")


if __name__ == "__main__":
    main()
