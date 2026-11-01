"""
C1 multi-turn understanding: slot extraction + dialogue state tracking.

Hybrid slot extractor (no training needed):
  - district           25-district gazetteer (English, romanized and Sinhala-script spellings)
  - date-type slots    pattern matcher (months, "next week", ලබන මාසේ, numbers) -> canonical English
  - fixed-choice slots keyword rules (applicant_for, change_field, urgency, service_type)
  - free text          service / purpose / complaint-type gazetteers, plus "answer to the bot's
                       question" (e.g. bot asks for the new address -> the whole reply is new_value)
  - optional           XLM-R NER spans (from c1_xlmr_train.ipynb models) for free-text slots

Dialogue state tracker: carries slots across turns, applies corrections ("Kandy... sorry, Matale",
"18, 8 nemei"), yes/no answers to the bot's question, confirmations ("District eka Colombo neda?" -> "ow"),
and drops slots that the new intent does not use after an intent switch.

Used by experiments/dst_eval.py (evaluation) and later by the FastAPI service.
"""
import re
import unicodedata

# ---------------------------------------------------------------- schema (v1.1)
INTENT_SLOTS = {
    "nic_new": ["applicant_for", "district", "date_of_birth"],
    "nic_update": ["change_field", "new_value", "district"],
    "nic_replace_lost": ["district", "urgency"],
    "passport_new": ["applicant_for", "service_type", "travel_date"],
    "passport_renew": ["service_type", "travel_date"],
    "birth_cert_copy": ["applicant_for", "district", "purpose"],
    "marriage_registration": ["district", "date"],
    "death_cert_copy": ["district", "purpose"],
    "unsupported_service": ["service_mentioned"],
    "feedback_complaint": ["service_mentioned", "issue"],
    "general_question": ["service_mentioned"],
    "out_of_scope": [],
}
DATE_SLOT = {"passport_new": "travel_date", "passport_renew": "travel_date",
             "marriage_registration": "date", "nic_new": "date_of_birth"}
SERVICE_OF_INTENT = {"nic_new": "NIC", "nic_update": "NIC", "nic_replace_lost": "NIC", "passport_new": "passport",
                     "passport_renew": "passport", "birth_cert_copy": "birth certificate",
                     "marriage_registration": "marriage registration", "death_cert_copy": "death certificate"}
FREE_TEXT = {"new_value", "purpose", "service_mentioned", "issue"}
DATE_SLOTS = {"date", "travel_date", "date_of_birth"}

TRIM = ".,?!…;:\"'()"


def norm(s):
    return unicodedata.normalize("NFC", s or "")


def words_with_offsets(text):
    """Same word splitting as the labelling scripts."""
    text = norm(text)
    for m in re.finditer(r"\S+", text):
        raw, start = m.group(), m.start()
        lead = len(raw) - len(raw.lstrip(TRIM))
        w = raw.strip(TRIM)
        if w:
            yield w, start + lead, start + lead + len(w)


def low(w):
    return norm(w).lower()


def is_sinhala(w):
    return any("඀" <= c <= "෿" for c in w)


def starts(word, variant):
    """Word matches a gazetteer entry. Sinhala and romanized words may carry case endings
    (ගාල්ලේ, කුරුණෑගලට, Colombowala), so a long-enough entry also matches as a prefix."""
    w, v = low(word), low(variant)
    if w == v:
        return True
    min_len = 3 if is_sinhala(v) else 5
    return len(v) >= min_len and w.startswith(v) and len(w) - len(v) <= 5


# ---------------------------------------------------------------- gazetteers
DISTRICTS = {
    "Colombo": ["colombo", "kolamba", "kolomba", "කොළඹ"],
    "Gampaha": ["gampaha", "ගම්පහ"],
    "Kalutara": ["kalutara", "kaluthara", "කළුතර", "කලුතර"],
    "Kandy": ["kandy", "mahanuwara", "මහනුවර"],
    "Matale": ["matale", "mathale", "මාතලේ", "මාතලෙ"],
    "Nuwara Eliya": ["nuwara eliya", "nuwaraeliya", "nuwara-eliya", "නුවරඑළිය", "නුවර එළිය"],
    "Galle": ["galle", "galla", "gaalla", "ගාල්ල"],
    "Matara": ["matara", "mathara", "මාතර"],
    "Hambantota": ["hambantota", "hambanthota", "හම්බන්තොට"],
    "Jaffna": ["jaffna", "yapanaya", "යාපනය"],
    "Kilinochchi": ["kilinochchi", "කිලිනොච්චිය", "කිලිනොච්චි"],
    "Mannar": ["mannar", "mannarama", "මන්නාරම"],
    "Vavuniya": ["vavuniya", "wawuniya", "වවුනියාව"],
    "Mullaitivu": ["mullaitivu", "mulathivu", "mullativu", "මුලතිව්"],
    "Batticaloa": ["batticaloa", "madakalapuwa", "මඩකලපුව"],
    "Ampara": ["ampara", "අම්පාර"],
    "Trincomalee": ["trincomalee", "trinco", "thirikunamalaya", "ත්‍රිකුණාමලය"],
    "Kurunegala": ["kurunegala", "kurunagala", "කුරුණෑගල", "කුරුනෑගල"],
    "Puttalam": ["puttalam", "puttalama", "puththalama", "පුත්තලම"],
    "Anuradhapura": ["anuradhapura", "anuradapura", "anuradhapuraya", "අනුරාධපුර"],
    "Polonnaruwa": ["polonnaruwa", "pollonnaruwa", "පොළොන්නරුව", "පොලොන්නරුව"],
    "Badulla": ["badulla", "බදුල්ල"],
    "Monaragala": ["monaragala", "moneragala", "මොණරාගල", "මොනරාගල"],
    "Ratnapura": ["ratnapura", "rathnapura", "රත්නපුර"],
    "Kegalle": ["kegalle", "kegalla", "කෑගල්ල"],
}

# canonical service names (as used in the gold labels) -> trigger words/phrases
SERVICES = [
    ("residence certificate", ["residence certificate", "grama niladhari certificate", "gn certificate",
                               "grama niladhari", "ග්‍රාම නිලධාරී", "residence"]),
    ("police clearance", ["police clearance", "police report", "පොලිස් වාර්තා", "පොලිස්", "police"]),
    ("driving license", ["driving license", "driving licence", "license", "licence", "රියදුරු බලපත්‍ර"]),
    ("business registration", ["business registration", "business", "company", "ව්‍යාපාර", "සමාගම"]),
    ("building permit", ["building permit", "permit", "ගොඩනැගිලි අවසර", "අවසරය"]),
    ("utility connection", ["current", "electricity", "water", "connection", "වතුර", "විදුලි", "ජලය",
                            "සම්බන්ධතා"]),
    ("birth certificate", ["birth certificate", "birth cert", "උප්පැන්න"]),
    ("death certificate", ["death certificate", "death cert", "මරණ සහතික"]),
    ("marriage registration", ["marriage", "විවාහ"]),
    ("passport", ["passport", "pp", "ගමන් බලපත්‍ර"]),
    ("NIC", ["nic", "id", "identity card", "හැඳුනුම්පත", "ජාතික හැඳුනුම්පත"]),
]

# internal core intent -> KG service ID (research/data/kg_service_map.json, kg_service_id; marriage and death
# are proposed, pending C2). tests/test_projection.py checks the two agree.
KG_SERVICE_IDS = {
    "nic_new": "svc:nic", "nic_update": "svc:nic", "nic_replace_lost": "svc:nic",
    "passport_new": "svc:passport", "passport_renew": "svc:passport",
    "birth_cert_copy": "svc:birth_certificate",
    "marriage_registration": "svc:marriage_registration",
    "death_cert_copy": "svc:death_certificate",
}
# explicit service keywords per KG service: leaving the active intent for another core intent needs one of
# these for the new service in the message (engine.Session). Matched with gaz_find.
SERVICE_KEYWORDS = {
    "svc:nic": ["nic", "id", "id card", "identity card", "national identity card", "handunumpatha",
                "hendunumpatha", "handunumpath", "හැඳුනුම්පත", "හැදුනුම්පත", "ජාතික හැඳුනුම්පත"],
    "svc:passport": ["passport", "pass port", "gaman balapathraya", "gaman balapatraya", "ගමන් බලපත්‍ර",
                     "පාස්පෝට්"],
    "svc:birth_certificate": ["birth certificate", "birth cert", "uppenna", "uppanna", "upan sahathikaya",
                              "උප්පැන්න", "උප්පැන්න සහතික"],
    "svc:death_certificate": ["death certificate", "death cert", "marana sahathikaya", "maranaya", "මරණ සහතික",
                              "මරණ"],
    "svc:marriage_registration": ["marriage", "marriage certificate", "vivaha", "wiwaha", "විවාහ"],
}
# variant cues for the services with more than one core intent, checked in this order (a lost NIC that is
# applied for "aluthen" is still lost; "aluth karanna" is a renewal). A message that names the service with none
# of these gets "which one?" instead of the classifier's guess (engine.Session). "ganna" / "apply" (get, apply
# for) count as new: "passport ekak ganna one".
VARIANT_KEYWORDS = {
    "svc:nic": [
        ("nic_replace_lost", ["lost", "lose", "missing", "stolen", "replace", "replacement", "duplicate", "nathiuna",
                              "nathi una", "nathi unaa", "nathi wuna", "nathi vuna", "nathi wela", "naathi una",
                              "naathi wela", "naathi wuna", "නැති වුණා", "නැතිවුණා", "නැති උනා", "නැති වුණු",
                              "නැති වෙලා"]),
        ("nic_update", ["update", "updated", "change", "changed", "correction", "amend", "wenas", "venas",
                        "wenaskaranna", "වෙනස්", "යාවත්කාලීන"]),
        ("nic_new", ["new", "aluth", "aluthen", "alut", "first", "palamu", "palaweni", "ganna", "apply", "අලුත්",
                     "අලුතෙන්", "පළමු", "ගන්න"]),
    ],
    "svc:passport": [
        ("passport_renew", ["renew", "renewal", "re-new", "expire", "expired", "expiring", "ikuth", "kal ikuth",
                            "aluth karanna", "aluth karaganna", "අලුත් කරන්න", "අලුත් කරගන්න", "කල් ඉකුත්", "ඉකුත්"]),
        ("passport_new", ["new", "aluth", "alut", "first", "palamu", "palaweni", "ganna", "apply", "අලුත්", "පළමු",
                          "ගන්න"]),
    ],
}

# purpose is only filled from this list (free text is not accepted: "for my daughter" is not a purpose)
PURPOSES = [
    ("school admission", ["school", "පාසල්", "පාසලට", "ඉස්කෝල"]),
    ("land transfer", ["idam", "land", "ඉඩම්", "ඉඩම", "deed", "oppuwa", "ඔප්පුව"]),
    ("bank", ["bank", "බැංකු", "account"]),
    ("visa", ["visa", "වීසා", "විසා"]),
    ("passport", ["passport", "ගමන් බලපත්‍ර"]),
    ("NIC", ["nic", "id", "හැඳුනුම්පත"]),
    ("job", ["job", "rakiyawa", "රැකියා", "army"]),
    ("foreign employment", ["foreign employment", "foreign job", "rata rassawa"]),
    ("going abroad", ["abroad", "going abroad", "pitarata", "පිටරට"]),
    ("pension", ["pension", "විශ්‍රාම", "wishrama"]),
    ("EPF", ["epf", "etf"]),
    ("insurance", ["insurance", "රක්ෂණ"]),
    ("court case", ["court", "nadu", "උසාවි"]),
    ("exam", ["exam", "a/l", "o/l", "විභාග"]),
    ("scholarship", ["scholarship", "ශිෂ්‍යත්ව"]),
    ("marriage", ["marriage", "vivaha", "විවාහ"]),
]

# complaint categories (feedback_complaint -> issue). A small taxonomy of common complaint types.
ISSUES = [
    ("extra document required", ["document", "ලේඛන", "doc"]),
    ("fee different", ["fee", "fees", "ගාස්තු", "ගාස්තුව", "salli", "සල්ලි", "වැඩියෙන්"]),
    ("office hours wrong", ["open", "closed", "wahala", "වහලා", "hours", "saturday", "sunday"]),
    ("photo count wrong", ["photo", "ඡායාරූප", "pinthura"]),
]

APPLICANT = [
    ("child", ["putha", "puthage", "putage", "puta", "putata", "puthata", "duwa", "duwage", "duwata", "lamaya",
               "lamayage", "lamayata", "daruwa", "daruwage", "son", "daughter", "child", "kid", "baby", "babyge",
               "පුතා", "පුතාට", "පුතාගේ", "දුව", "දුවට", "දුවගේ", "ළමයා", "ළමයාට", "දරුවා", "දරුවාට", "දරුවාගේ"]),
    ("parent", ["amma", "ammage", "ammata", "thaththa", "thaththage", "thaththata", "appachchi", "mother", "father",
                "mom", "dad", "අම්මා", "අම්මාගේ", "අම්මාට", "අම්මට", "අම්මගේ", "තාත්තා", "තාත්තාගේ", "තාත්තාට",
                "තාත්තට", "තාත්තගේ"]),
    ("spouse", ["wife", "husband", "birida", "biridage", "mahaththaya", "mahaththayage", "බිරිඳ", "බිරිඳට",
                "බිරිඳගේ", "සැමියා", "සැමියාට", "මහත්තයා"]),
    # siblings: romanized forms match whole words, so each case ending is listed; Sinhala-script forms match
    # as prefixes (නංගි covers නංගිට), but අක්කට / අයියට do not start with අක්කා / අයියා
    ("other", ["malli", "mallige", "mallita", "malliita", "malliata", "malliage", "nangi", "nangige", "nangita",
               "nangiata", "ayya", "ayyata", "ayyage", "akka", "akkata", "akkage", "brother", "sister", "seeya",
               "aachchi", "මල්ලි", "නංගි", "අයියා", "අයියට", "අයියගේ", "අක්කා", "අක්කට", "අක්කගේ", "සීයා", "ආච්චි",
               "friend", "yaluwa"]),
    # "mata" (for me), "mage" (my), "my", "me": the request is for the speaker. A bare subject pronoun
    # ("i need...", "mama", "මම") is not evidence: "i need a birth certificate" can be for a daughter.
    ("self", ["mata", "mage", "my", "me", "myself", "for me", "මට", "මගේ"]),
]

CHANGE_FIELD = [
    ("address", ["address", "lipinaya", "ලිපිනය", "ලිපිනේ", "ලිපින"]),
    ("name", ["name", "nama", "surname", "නම", "නමේ", "වාසගම"]),
    ("photo", ["photo", "pinthura", "ඡායාරූපය", "ඡායාරූප", "photo eka"]),
    ("civil_status", ["civil", "marital", "vivaha", "විවාහ"]),
]

URGENT = ["urgent", "urgently", "ikmanata", "ikmanin", "ikmanta", "hadissi", "hadissiye", "hadisi", "one day",
          "oneday", "same day", "ඉක්මනට", "ඉක්මනින්", "ඉක්මනින්ම", "හදිසි", "එක දින", "එක් දින"]
NORMAL = ["normal", "සාමාන්‍ය", "sāmānya", "ordinary"]

AFFIRM = {"ow", "owu", "ov", "yes", "yeah", "yep", "ඔව්", "ඔව්.", "hari", "හරි", "ok", "okay", "ehemai", "එහෙමයි"}
DENY = {"na", "naa", "nehe", "nae", "no", "nope", "නෑ", "නැහැ", "නැ", "nathi"}
# words that cancel the mention just before them ("Kandy... sorry, Matale", "Canada nemei")
NEG_AFTER = {"nemei", "nemeyi", "newei", "nevei", "නෙවෙයි", "නෙමෙයි", "නෙවේ", "parana", "පරණ", "sorry", "sry",
             "නෑ", "නැහැ", "not", "no", "na"}

# ------------------------------------------------------------- date canonicaliser
MONTHS = {
    "january": ["january", "jan", "ජනවාරි"], "february": ["february", "feb", "පෙබරවාරි"],
    "march": ["march", "mar", "මාර්තු"], "april": ["april", "apr", "අප්‍රේල්"],
    "may": ["may", "මැයි"], "june": ["june", "jun", "ජූනි"], "july": ["july", "jul", "ජූලි"],
    "august": ["august", "aug", "අගෝස්තු"], "september": ["september", "sep", "sept", "සැප්තැම්බර්"],
    "october": ["october", "oct", "ඔක්තෝබර්"], "november": ["november", "nov", "නොවැම්බර්"],
    "december": ["december", "dec", "දෙසැම්බර්"],
}
DATE_WORDS = {
    "next": ["next", "labana", "ලබන", "ilanga", "ඊළඟ", "ilaga"],
    "this": ["this", "me", "මේ"],
    "week": ["week", "sathiye", "sathiya", "sathi", "සතියේ", "සතිය", "සතියෙ"],
    "month": ["month", "mase", "maase", "masaye", "මාසේ", "මාසයේ", "මාසෙ", "මාසය"],
    "year": ["year", "yr", "awurudde", "awurudu", "අවුරුද්දේ", "අවුරුද්ද"],
    "tomorrow": ["tomorrow", "heta", "හෙට"],
    "today": ["today", "ada", "අද"],
    "mid": ["mid", "middle", "meda", "මැද"],
    "end": ["end", "anthime", "අන්තිම", "අග"],
}
_DATE_LOOKUP = {}
for canon, forms in {**MONTHS, **DATE_WORDS}.items():
    for f in forms:
        _DATE_LOOKUP[low(f)] = canon
# words that only count as date words next to another date word (to avoid "me" = this, "ada" = today noise)
WEAK_DATE = {"this", "today", "next", "mid", "end"}


def date_token(w):
    lw = low(w)
    if lw in _DATE_LOOKUP:
        return _DATE_LOOKUP[lw]
    if re.fullmatch(r"\d{1,2}(st|nd|rd|th)?", lw):
        return re.sub(r"\D", "", lw)
    if re.fullmatch(r"(19|20)\d\d", lw):
        return lw
    if re.fullmatch(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}", lw):
        return lw
    return None


def canon_date(text):
    """Canonical token set for comparing date values: 'december mid eke' == 'mid December'."""
    toks = [date_token(w) for w, _, _ in words_with_offsets(text)]
    toks = [t for t in toks if t]
    return " ".join(sorted(set(toks))) if toks else low(text).strip()


# ---------------------------------------------------------------- value comparison
def canon_text(s):
    s = low(s)
    s = re.sub(r"[^\w඀-෿/ ]", " ", s)
    s = re.sub(r"\b(eka|ekata|eke|ekak|එක|එකට|එකේ|එකක්)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def canon_value(slot, v):
    if v is None:
        return None
    v = norm(str(v))
    if slot in DATE_SLOTS:
        return canon_date(v)
    if slot in ("service_type", "urgency"):
        return {"one_day": "urgent"}.get(v.lower(), v.lower())
    if slot == "purpose":
        hit = gaz_find(v, PURPOSES)
        return hit[0] if hit else canon_text(v)
    if slot == "service_mentioned":
        hit = gaz_find(v, SERVICES)
        return hit[0] if hit else canon_text(v)
    if slot in FREE_TEXT:
        return canon_text(v)
    return v.strip().lower()


def values_match(slot, pred, gold, relaxed=True):
    a, b = canon_value(slot, pred), canon_value(slot, gold)
    if a == b:
        return True
    if relaxed and slot in FREE_TEXT and a and b:
        return a in b or b in a
    return False


def states_match(pred, gold, relaxed=True, skip=()):
    keys = (set(pred) | set(gold)) - set(skip)
    return all(k in pred and k in gold and values_match(k, pred[k], gold[k], relaxed) for k in keys)


# ---------------------------------------------------------------- matching helpers
def _words(text):
    return list(words_with_offsets(text))


def gaz_find(text, gazetteer, words=None, last=True):
    """Find gazetteer entries (single or multi-word). Returns (canonical, start_word, end_word) of the
    last (or first) match, or None. Longer phrases win at the same position."""
    ws = words if words is not None else _words(text)
    lw = [low(w) for w, _, _ in ws]
    hits = []
    for canon, forms in gazetteer:
        for f in forms:
            parts = low(f).split()
            n = len(parts)
            for i in range(len(lw) - n + 1):
                ok = all(lw[i + k] == parts[k] for k in range(n - 1)) and starts(ws[i + n - 1][0], parts[-1]) \
                    if n > 1 else starts(ws[i][0], parts[0])
                if ok:
                    hits.append((i, -n, canon, i + n))
    if not hits:
        return None
    hits.sort()
    if last:
        best_start = max(h[0] for h in hits)
        h = sorted(x for x in hits if x[0] == best_start)[0]
    else:
        h = hits[0]
    return h[2], h[0], h[3]


def negated_after(lw, end):
    return any(w in NEG_AFTER for w in lw[end:end + 1])


def find_district(words, skip_negated=True):
    lw = [low(w) for w, _, _ in words]
    mentions = []
    for canon, forms in DISTRICTS.items():
        for f in forms:
            parts = f.split()
            n = len(parts)
            for i in range(len(lw) - n + 1):
                if all(starts(words[i + k][0], parts[k]) if k == n - 1 else lw[i + k] == parts[k] for k in range(n)):
                    mentions.append((i, i + n, canon))
    mentions = sorted(set(mentions))
    # drop a shorter mention inside a longer one (nuwara inside nuwara eliya)
    mentions = [m for m in mentions if not any(o != m and o[0] <= m[0] and m[1] <= o[1] for o in mentions)]
    kept = [m for m in mentions if not (skip_negated and negated_after(lw, m[1]))]
    return kept[-1] if kept else None


def find_date(words):
    """Last run of date words that is not cancelled by a following 'no/sorry'."""
    toks = [date_token(w) for w, _, _ in words]
    lw = [low(w) for w, _, _ in words]
    runs, i = [], 0
    while i < len(toks):
        if toks[i]:
            j = i
            while j < len(toks) and toks[j]:
                j += 1
            run = toks[i:j]
            # a run counts as a date if it has a month name, week/month/tomorrow, a year number or a full
            # date, or "year" with next/this. A bare number ("16") or "awurudu 16" is an age, not a date.
            strong = [t for t in run if t in MONTHS or t in ("week", "month", "tomorrow")
                      or re.fullmatch(r"(19|20)\d\d|\d+[/-]\d+[/-]\d+", t)]
            if "year" in run and ("next" in run or "this" in run):
                strong.append("year")
            if strong:
                runs.append((i, j))
            i = j
        else:
            i += 1
    runs = [r for r in runs if not negated_after(lw, r[1])]
    if not runs:
        return None
    s, e = runs[-1]
    return " ".join(w for w, _, _ in words[s:e]), s, e


def has_any(words, forms):
    lw = [low(w) for w, _, _ in words]
    text = " " + " ".join(lw) + " "
    for f in forms:
        f = low(f)
        if " " in f:
            if f" {f} " in text:
                return True
        elif any(starts(w, f) if is_sinhala(f) else w == f for w in lw):
            return True
    return False


def first_word(words):
    return low(words[0][0]) if words else ""


def requested_slot(bot_text, intent):
    """Which slot the bot's last question asks for."""
    b = low(bot_text or "")
    if not b:
        return None
    if re.search(r"district|දිස්ත්‍රික්ක|kohe|koheda|kohenda|කොහෙද|කොයි ප්‍රදේශ", b):
        return "district"
    if re.search(r"(aluth|අලුත්|new).*(address|lipina|ලිපින|nama|නම|name|mokakda|මොකක්ද)", b):
        return "new_value"
    if re.search(r"kage|kaageda|kageda|කාගේ|ඔයාටමද|වෙන කෙනෙක්|for whom|who is it for", b):
        return "applicant_for"
    if re.search(r"kawada|කවදද|when|date|දිනය", b):
        return DATE_SLOT.get(intent, "date")
    if re.search(r"ikman|ඉක්මන|urgent|one day|hadissi|හදිසි", b):
        return "service_type" if intent and intent.startswith("passport") else "urgency"
    if re.search(r"mokatada|මොකටද|why|purpose|කුමකටද", b):
        return "purpose"
    if re.search(r"service|සේවා|office|කාර්යාල", b):
        return "service_mentioned"
    return None


def bot_proposed_district(bot_text):
    """'District eka Colombo neda?' -> 'Colombo' (a value the user can confirm with 'ow')."""
    if not bot_text:
        return None
    b = low(bot_text)
    if not re.search(r"neda|නේද|\bda\?|\bද\?|isn't it|right\?|correct\?", b):
        return None
    hit = find_district(_words(bot_text), skip_negated=False)
    return hit[2] if hit else None


# a pronoun that points back to the person of the previous request ("eyata ID eka ganna" after a daughter's
# birth certificate): on an intent switch, applicant_for is carried only when one of these is in the message
BACK_REFERENCE = ["eyata", "eyage", "එයාට", "එයාගේ", "for her", "for him"]


def refers_back(text):
    return has_any(_words(text), BACK_REFERENCE)


def variant_cue(text, service):
    """The core intent a variant cue in the message points to for this KG service, or None."""
    words = _words(text)
    return next((intent for intent, forms in VARIANT_KEYWORDS.get(service, []) if has_any(words, forms)), None)


# ---------------------------------------------------------------- condition facts
# Facts about the applicant that are not slots: never asked for, only kept when the citizen says them ("she is
# 14 years still"). C1 only records them; what they mean for the application is C2's decision.
ADULT_AGE = 18
AGE_BEFORE = {"is", "am", "age", "aged", "wayasa", "vayasa", "වයස", "වයස්", "avurudu", "awurudu", "අවුරුදු"}
AGE_AFTER = {"year", "years", "yr", "yrs", "yo", "y/o", "old", "avurudu", "awurudu", "අවුරුදු"}
NOT_AGE_BEFORE = {"for", "in", "within", "after", "last", "past", "under", "below", "over", "above", "valid"}
NOT_AGE_AFTER = {"ago", "kalin", "kalinda", "before", "back", "passe", "කලින්", "පස්සේ"}
# a number next to these is an address, a date or an ID number ("No. 14, Temple Road", "my number is 14")
NUMBER_CONTEXT = {"no", "number", "num", "house", "address", "lipinaya", "road", "lane", "mawatha", "date",
                  "dinaya", "day", "nic", "id", "phone"}
MINOR = ["under 18", "below 18", "under age", "underage", "under-age", "18ta adu", "18ට අඩු", "bala wayaskara",
         "බාල වයස්කාර"]
NOT_MINOR_AFTER = {"change", "changes", "correction", "mistake", "error", "issue", "problem"}   # "minor correction"
_AGE_NUM = re.compile(r"(\d{1,3})(i|yi|යි)?")


def find_age(words):
    """'she is 14', '14 years', 'avurudu 14', 'wayasa 14i' -> 14. Dates, addresses and ID numbers are skipped."""
    lw = [low(w) for w, _, _ in words]
    for i, w in enumerate(lw):
        m = _AGE_NUM.fullmatch(w)
        if not m:
            continue
        age, before, after = int(m.group(1)), lw[i - 1] if i else "", lw[i + 1:i + 3]
        if not 0 < age < 120 or before in NOT_AGE_BEFORE or set(lw[max(0, i - 2):i]) & NUMBER_CONTEXT \
                or set(after) & NOT_AGE_AFTER:
            continue
        if before in AGE_BEFORE or (after and after[0] in AGE_AFTER):
            return age
    return None


def extract_conditions(text):
    """Condition facts said in this message: {"applicant_age": 14, "applicant_minor": True}, or
    {"applicant_minor": True} for "minor" / "under 18" without an age."""
    words = _words(text)
    age = find_age(words)
    if age is not None:
        return {"applicant_age": age, "applicant_minor": age < ADULT_AGE}
    lw = [low(w) for w, _, _ in words] + [""]
    minor = any(w == "minor" and lw[i + 1] not in NOT_MINOR_AFTER for i, w in enumerate(lw[:-1]))
    if minor or has_any(words, MINOR):
        return {"applicant_minor": True}
    return {}


def merge_conditions(old, new):
    """A new age replaces the old one; "minor" alone drops an adult age said before."""
    out = dict(old)
    if "applicant_age" in new:
        out.update(new)
    elif new.get("applicant_minor"):
        if out.get("applicant_age", 0) >= ADULT_AGE:
            out.pop("applicant_age")
        out["applicant_minor"] = True
    return out


def other_slot_evidence(text, words, allowed, requested, prev_state=None):
    """Fixed-choice (keyword) slots other than `requested` that the message matches ("for my daughter" ->
    applicant_for). Free text is only put into the requested slot when this is empty. Not checked, because
    they are normal inside a free-text value: districts and dates ("No 12, Main Street, Kandy"), "my"/"mata"
    ("my husband's surname"), and the field already being changed ("aluth address eka No. 45 ...")."""
    current_field = (prev_state or {}).get("change_field")
    checks = {
        "applicant_for": lambda: any(has_any(words, forms) for canon, forms in APPLICANT if canon != "self"),
        "change_field": lambda: any(has_any(words, forms) for canon, forms in CHANGE_FIELD if canon != current_field),
        "urgency": lambda: has_any(words, URGENT) or has_any(words, NORMAL),
        "service_type": lambda: has_any(words, URGENT) or has_any(words, NORMAL),
        "purpose": lambda: gaz_find(text, PURPOSES, words) is not None,
    }
    return {slot for slot, check in checks.items() if slot != requested and slot in allowed and check()}


# ---------------------------------------------------------------- extractor
class SlotExtractor:
    """Per-turn slot values. use_context=False ignores the bot's question (ablation)."""

    def __init__(self, use_context=True, use_negation=True, ner=None):
        self.use_context = use_context
        self.use_negation = use_negation
        self.ner = ner  # optional callable(text) -> [{"type","text","start","end"}]

    def extract(self, text, intent, bot_text=None, prev_state=None):
        """Returns {slot: {"value", "start", "end"}} with character offsets (None for turn-level labels)."""
        allowed = set(INTENT_SLOTS.get(intent, []))
        words = _words(text)
        out = {}
        req = requested_slot(bot_text, intent) if self.use_context else None
        fw = first_word(words)
        # the answer belongs to another slot ("for my daughter" to "what is it for?"): no free text for req
        free_text_ok = bool(req) and not other_slot_evidence(text, words, allowed, req, prev_state)

        def put(slot, value, s=None, e=None):
            if slot in allowed and value:
                cs = words[s][1] if s is not None else None
                ce = words[e - 1][2] if e is not None else None
                out[slot] = {"value": value, "start": cs, "end": ce}

        # district
        if "district" in allowed and req != "new_value":
            hit = find_district(words, skip_negated=self.use_negation)
            if hit:
                put("district", hit[2], hit[0], hit[1])
            elif self.use_context and fw in AFFIRM:
                prop = bot_proposed_district(bot_text)
                if prop:
                    put("district", prop)

        # dates
        dslot = DATE_SLOT.get(intent)
        expiry = any(low(w).startswith(("expir", "ඉකුත්", "kal ikuth")) for w, _, _ in words)
        if dslot and dslot in allowed and not (dslot == "travel_date" and expiry):
            hit = find_date(words) if self.use_negation else self._first_date(words)
            if hit:
                put(dslot, hit[0], hit[1], hit[2])

        # applicant_for (self only when nothing more specific and the slot is still empty)
        if "applicant_for" in allowed:
            for canon, forms in APPLICANT:
                if canon == "self" and prev_state and prev_state.get("applicant_for"):
                    continue
                if has_any(words, forms):
                    put("applicant_for", canon)
                    break

        # change_field
        if "change_field" in allowed:
            for canon, forms in CHANGE_FIELD:
                if has_any(words, forms):
                    put("change_field", canon)
                    break

        # urgency / service_type
        for slot in ("urgency", "service_type"):
            if slot not in allowed:
                continue
            urgent_value = "urgent"
            if has_any(words, NORMAL):
                put(slot, "normal")
            elif has_any(words, URGENT) and not (fw in DENY and req == slot):
                put(slot, urgent_value)
            elif self.use_context and req == slot:
                if fw in AFFIRM or low(text).startswith(("ow", "ඔව්", "yes")):
                    put(slot, urgent_value)
                elif fw in DENY:
                    put(slot, "normal")

        # new_value: the whole answer to "what is the new address/name?"
        if "new_value" in allowed and self.use_context and req == "new_value" and words and free_text_ok:
            put("new_value", text.strip().strip(TRIM), 0, len(words))

        # purpose
        if "purpose" in allowed:
            hit = gaz_find(text, PURPOSES, words)
            if hit:
                put("purpose", hit[0], hit[1], hit[2])

        # service_mentioned
        if "service_mentioned" in allowed:
            hit = gaz_find(text, SERVICES, words)
            if hit:
                put("service_mentioned", hit[0], hit[1], hit[2])
            elif self.use_context and req == "service_mentioned" and words and free_text_ok:
                put("service_mentioned", canon_text(text), 0, len(words))

        # issue (complaint type)
        if "issue" in allowed:
            hit = gaz_find(text, ISSUES, words, last=False)
            if hit:
                put("issue", hit[0], hit[1], hit[2])

        # optional XLM-R entities fill free-text slots the rules missed (purpose only from the keyword list,
        # and never the requested slot when the answer belongs to another slot)
        if self.ner:
            for ent in self.ner(text):
                slot = ent["type"]
                if slot not in allowed or slot in out or slot == "district":
                    continue
                if slot == "purpose" and not gaz_find(ent["text"], PURPOSES):
                    continue
                if slot == req and not free_text_ok:
                    continue
                out[slot] = {"value": ent["text"], "start": ent["start"], "end": ent["end"]}
        return out

    @staticmethod
    def _first_date(words):
        toks = [date_token(w) for w, _, _ in words]
        for i, t in enumerate(toks):
            if t and (t in MONTHS or t in ("week", "month", "tomorrow") or re.fullmatch(r"(19|20)\d\d", t)):
                j = i
                while j < len(toks) and toks[j]:
                    j += 1
                return " ".join(w for w, _, _ in words[i:j]), i, j
        return None


# ---------------------------------------------------------------- state tracker
NUM_FIX = re.compile(r"(\d+[\w/]*)\s*,?\s*(\d+[\w/]*)\s*(nemei|nemeyi|newei|nevei|නෙවෙයි|නෙමෙයි|not)", re.I)


class DialogueStateTracker:
    """
    carryover=False      : state = this turn's slots only (no memory)
    switch_filter=True   : an intent switch starts a new slot frame; only district is carried, and it stays
                           in `assumed` until the citizen restates or confirms it. applicant_for is carried
                           too when the message points back to that person ("eyata", BACK_REFERENCE)
    corrections=True     : apply in-turn number corrections to new_value ("18, 8 nemei")

    `conditions` holds facts about the applicant that are not slots (applicant_age, applicant_minor): kept when
    said, never asked for, and carried to a new request only under the same back-reference rule as applicant_for.
    They are not part of the JGA state.
    """

    def __init__(self, extractor, carryover=True, switch_filter=True, corrections=True):
        self.x = extractor
        self.carryover = carryover
        self.switch_filter = switch_filter
        self.corrections = corrections
        self.reset()

    def reset(self):
        self.intent = None
        self.slots = {}
        self.spans = {}
        self.assumed = set()        # carried slots the citizen has not confirmed for the current intent
        self.conditions = {}        # condition facts about the applicant (not slots)

    def update(self, text, intent, bot_text=None, frame=None):
        """frame: the slots to start from when the caller prepared them (engine.Session restores a request the
        citizen comes back to, and sets `conditions` itself); None = carry over from the previous turn."""
        prev = dict(self.slots) if self.carryover else {}
        conditions = dict(self.conditions) if self.carryover else {}
        if frame is not None:
            prev = dict(frame)
        elif self.switch_filter and intent != self.intent:
            back = refers_back(text)
            carry = {"district", "applicant_for"} if back else {"district"}
            prev = {k: v for k, v in prev.items() if k in carry and k in INTENT_SLOTS.get(intent, [])}
            self.assumed = set(prev) & {"district"}
            if not back:
                conditions = {}
        self.conditions = merge_conditions(conditions, extract_conditions(text))
        new = self.x.extract(text, intent, bot_text, prev)
        self.assumed -= set(new)    # restated or corrected this turn
        if self.corrections and "new_value" in prev and "new_value" not in new:
            m = NUM_FIX.search(norm(text))
            if m:
                new_num, old_num = m.group(1), m.group(2)
                fixed = re.sub(rf"(?<![\w/]){re.escape(old_num)}(?![\w/])", new_num, prev["new_value"], count=1)
                if fixed != prev["new_value"]:
                    new["new_value"] = {"value": fixed, "start": None, "end": None}
        # a complaint or question right after a service request is about that service
        if intent in ("feedback_complaint", "general_question") and "service_mentioned" not in new \
                and self.intent in SERVICE_OF_INTENT and intent != self.intent:
            new["service_mentioned"] = {"value": SERVICE_OF_INTENT[self.intent], "start": None, "end": None}
        state = dict(prev)
        for k, v in new.items():
            state[k] = v["value"]
        self.intent, self.slots = intent, state
        self.spans = new
        return {"intent": intent, "slots": dict(state), "conditions": dict(self.conditions)}

    def missing_slots(self):
        return [s for s in INTENT_SLOTS.get(self.intent, []) if s not in self.slots]


# ---------------------------------------------------------------- session helpers (engine.Session only)
# Not used by the tracker or dst_eval.py, so the JGA results are unchanged.
UNKNOWN_VALUE = "unknown"       # slot value when the citizen says they don't know

# major towns / DS divisions that are not district names -> (district, spellings). Romanized entries are
# stems where the ending changes ("wennappuw" matches wennappuwa, wennappuwe, wennappuwata); Sinhala-script
# entries match with case endings (ගාල්ලේ) through starts().
TOWNS = {
    # Colombo
    "Moratuwa": ("Colombo", ["moratuw", "මොරටුව"]),
    "Dehiwala": ("Colombo", ["dehiwala", "dehiwal", "දෙහිවල"]),
    "Mount Lavinia": ("Colombo", ["mount lavinia", "galkissa", "ගල්කිස්ස"]),
    "Maharagama": ("Colombo", ["maharagam", "මහරගම"]),
    "Nugegoda": ("Colombo", ["nugegod", "නුගේගොඩ"]),
    "Kotte": ("Colombo", ["kotte", "කෝට්ටේ"]),
    "Battaramulla": ("Colombo", ["battaramull", "බත්තරමුල්ල"]),
    "Kaduwela": ("Colombo", ["kaduwel", "කඩුවෙල"]),
    "Homagama": ("Colombo", ["homagam", "හෝමාගම"]),
    "Piliyandala": ("Colombo", ["piliyandal", "පිළියන්දල"]),
    "Avissawella": ("Colombo", ["avissawell", "awissawell", "අවිස්සාවේල්ල"]),
    "Kolonnawa": ("Colombo", ["kolonnaw", "කොලොන්නාව"]),
    # Gampaha
    "Negombo": ("Gampaha", ["negombo", "meegamuw", "migamuw", "මීගමුව"]),
    "Wattala": ("Gampaha", ["wattal", "වත්තල"]),
    "Ja-Ela": ("Gampaha", ["ja-ela", "jaela", "ජා-ඇල", "ජාඇල"]),
    "Kadawatha": ("Gampaha", ["kadawath", "කඩවත"]),
    "Kiribathgoda": ("Gampaha", ["kiribathgod", "කිරිබත්ගොඩ"]),
    "Minuwangoda": ("Gampaha", ["minuwangod", "මිනුවන්ගොඩ"]),
    "Kelaniya": ("Gampaha", ["kelaniy", "කැලණිය"]),
    # Kalutara
    "Panadura": ("Kalutara", ["panadur", "පානදුර"]),
    "Horana": ("Kalutara", ["horana", "horane", "හොරණ"]),
    "Beruwala": ("Kalutara", ["beruwal", "බේරුවල"]),
    "Matugama": ("Kalutara", ["matugam", "mathugam", "මතුගම"]),
    "Aluthgama": ("Kalutara", ["aluthgam", "අළුත්ගම", "අලුත්ගම"]),
    # Puttalam
    "Wennappuwa": ("Puttalam", ["wennappuw", "wennapuw", "වෙන්නප්පුව"]),
    "Chilaw": ("Puttalam", ["chilaw", "halawath", "හලාවත"]),
    "Marawila": ("Puttalam", ["marawil", "මාරවිල"]),
    "Nattandiya": ("Puttalam", ["nattandiy", "naththandiy", "නාත්තණ්ඩිය"]),
    "Dankotuwa": ("Puttalam", ["dankotuw", "දංකොටුව"]),
    # Kurunegala
    "Kuliyapitiya": ("Kurunegala", ["kuliyapitiy", "කුලියාපිටිය"]),
    "Narammala": ("Kurunegala", ["narammal", "නාරම්මල"]),
    "Pannala": ("Kurunegala", ["pannal", "පන්නල"]),
    "Wariyapola": ("Kurunegala", ["wariyapol", "වාරියපොල"]),
    "Polgahawela": ("Kurunegala", ["polgahawel", "පොල්ගහවෙල"]),
    # Kandy
    "Gampola": ("Kandy", ["gampol", "ගම්පොළ", "ගම්පොල"]),
    "Peradeniya": ("Kandy", ["peradeniy", "පේරාදෙණිය"]),
    "Katugastota": ("Kandy", ["katugastot", "කටුගස්තොට"]),
    "Nawalapitiya": ("Kandy", ["nawalapitiy", "නාවලපිටිය"]),
    "Kundasale": ("Kandy", ["kundasale", "කුණ්ඩසාලේ"]),
    # Matale
    "Dambulla": ("Matale", ["dambull", "දඹුල්ල"]),
    "Galewela": ("Matale", ["galewel", "ගලේවෙල"]),
    # Nuwara Eliya
    "Hatton": ("Nuwara Eliya", ["hatton", "හැටන්"]),
    "Talawakele": ("Nuwara Eliya", ["talawakel", "තලවාකැලේ"]),
    # Galle
    "Hikkaduwa": ("Galle", ["hikkaduw", "හික්කඩුව"]),
    "Ambalangoda": ("Galle", ["ambalangod", "අම්බලන්ගොඩ"]),
    "Elpitiya": ("Galle", ["elpitiy", "ඇල්පිටිය"]),
    "Baddegama": ("Galle", ["baddegam", "බද්දේගම"]),
    # Matara
    "Weligama": ("Matara", ["weligam", "වැලිගම"]),
    "Akuressa": ("Matara", ["akuress", "අකුරැස්ස"]),
    "Dikwella": ("Matara", ["dikwell", "දික්වැල්ල"]),
    # Hambantota
    "Tangalle": ("Hambantota", ["tangall", "thangall", "තංගල්ල"]),
    "Ambalantota": ("Hambantota", ["ambalantot", "අම්බලන්තොට"]),
    "Tissamaharama": ("Hambantota", ["tissamaharam", "tissa", "තිස්සමහාරාම"]),
    # Ratnapura
    "Embilipitiya": ("Ratnapura", ["embilipitiy", "ඇඹිලිපිටිය"]),
    "Balangoda": ("Ratnapura", ["balangod", "බලංගොඩ"]),
    "Pelmadulla": ("Ratnapura", ["pelmadull", "පැල්මඩුල්ල"]),
    "Eheliyagoda": ("Ratnapura", ["eheliyagod", "ඇහැළියගොඩ"]),
    # Kegalle
    "Mawanella": ("Kegalle", ["mawanell", "මාවනැල්ල"]),
    "Warakapola": ("Kegalle", ["warakapol", "වරකාපොළ", "වරකාපොල"]),
    "Rambukkana": ("Kegalle", ["rambukkan", "රඹුක්කන"]),
    # Badulla
    "Bandarawela": ("Badulla", ["bandarawel", "බණ්ඩාරවෙල"]),
    "Haputale": ("Badulla", ["haputal", "හපුතලේ"]),
    "Welimada": ("Badulla", ["welimad", "වැලිමඩ"]),
    "Mahiyanganaya": ("Badulla", ["mahiyangan", "මහියංගනය"]),
    "Passara": ("Badulla", ["passar", "පස්සර"]),
    # Monaragala
    "Wellawaya": ("Monaragala", ["wellaway", "වැල්ලවාය"]),
    "Bibile": ("Monaragala", ["bibile", "බිබිලේ"]),
    "Buttala": ("Monaragala", ["buttal", "බුත්තල"]),
    "Kataragama": ("Monaragala", ["kataragam", "කතරගම"]),
    # Anuradhapura / Polonnaruwa
    "Kekirawa": ("Anuradhapura", ["kekiraw", "කැකිරාව"]),
    "Medawachchiya": ("Anuradhapura", ["medawachchiy", "මැදවච්චිය"]),
    "Kaduruwela": ("Polonnaruwa", ["kaduruwel", "කඩුරුවෙල"]),
    "Hingurakgoda": ("Polonnaruwa", ["hingurakgod", "හිඟුරක්ගොඩ"]),
    # East and North
    "Kalmunai": ("Ampara", ["kalmunai", "කල්මුණේ"]),
    "Akkaraipattu": ("Ampara", ["akkaraipattu", "අක්කරපත්තුව"]),
    "Kattankudy": ("Batticaloa", ["kattankudy", "කාත්තන්කුඩි"]),
    "Kinniya": ("Trincomalee", ["kinniya", "කින්නියා"]),
    "Chavakachcheri": ("Jaffna", ["chavakachcheri", "චාවකච්චේරි"]),
}
TOWN_DISTRICT = {town: district for town, (district, _) in TOWNS.items()}
_TOWN_GAZ = [(town, forms) for town, (_, forms) in TOWNS.items()]


def find_town(words):
    """Last town mention not cancelled by a following 'no/sorry' -> (town, district), or None."""
    hit = gaz_find("", _TOWN_GAZ, words)
    if not hit or negated_after([low(w) for w, _, _ in words], hit[2]):
        return None
    return hit[0], TOWN_DISTRICT[hit[0]]


DONT_KNOW = ["danne na", "danne naa", "danne nae", "danne nehe", "danna na", "danne nǣ", "dannē nǣ", "dannē na",
             "danne nathi", "mathaka na", "mathaka nehe", "i dont know", "i don't know", "dont know", "don't know",
             "do not know", "not sure", "idk", "no idea", "දන්නේ නෑ", "දන්නෙ නෑ", "දන්නේ නැහැ", "දන්නෙ නැහැ",
             "මතක නෑ", "මතක නැහැ"]
_DONT_KNOW_RE = re.compile(r"(?<![\w඀-෿])(" + "|".join(re.escape(norm(p)) for p in DONT_KNOW) + r")(?![\w඀-෿])")


def is_dont_know(text):
    return bool(_DONT_KNOW_RE.search(low(text).replace("’", "'")))


GREETINGS = {"hi", "hii", "hello", "helo", "hey", "hai", "halo", "ayubowan", "aayubowan", "ayubovan", "ආයුබෝවන්",
             "good", "morning", "afternoon", "evening", "gm", "there", "sir", "madam", "miss", "machan", "kohomada",
             "කොහොමද", "hari"}
_GREETING_WORDS = {"hi", "hii", "hello", "helo", "hey", "hai", "halo", "ayubowan", "aayubowan", "ayubovan",
                   "ආයුබෝවන්", "morning", "evening", "afternoon", "gm"}


def is_greeting(text):
    """The whole message is a greeting ("hi", "hello there", "ආයුබෝවන්", "good morning sir")."""
    words = [low(w) for w, _, _ in words_with_offsets(text)]
    return 0 < len(words) <= 4 and all(w in GREETINGS for w in words) and any(w in _GREETING_WORDS for w in words)
