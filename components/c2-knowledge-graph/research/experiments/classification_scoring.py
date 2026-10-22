"""SO1: change classification accuracy, against a labelled test set.

Real change events within the project window are scarce by construction (a crawl this
short observes few natural edits), so most cases here are constructed -- the same decision
the proposal itself already logs and states openly (Table 11, Sep 2026: "Construct labelled
controlled change events and state this openly"). One case (R1) is a genuine observed
change: the same URL crawled on two different dates, with a real text difference, not a
synthetic edit.

    python research/experiments/classification_scoring.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1] / "service"
sys.path.insert(0, str(SERVICE_DIR))
CRAWL = Path(__file__).resolve().parents[1] / "data" / "crawl"

from app.core.acquisition.fingerprint import ChangeKind, classify, fingerprint  # noqa: E402


@dataclass
class Case:
    id: str
    provenance: str  # "real" or "constructed"
    expected: ChangeKind
    prev_text: str | None
    prev_html: str | None
    cur_text: str
    cur_html: str
    note: str = ""


def _load_real_pair() -> Case:
    """A genuine page re-crawled on two different dates, with a real text difference."""
    key = "ca4c4c82aedbb9a2"  # pages_e.php?id=66, saved 2026-10-11 and 2026-10-12 -- found
    # by intersecting the two archive dates' saved pages (research/experiments output).
    d1, d2 = CRAWL / "archive" / "2026-10-11", CRAWL / "archive" / "2026-10-12"
    for f in d1.glob("*.md"):
        if (d2 / f.name).exists():
            key = f.stem
            break
    text1 = (d1 / f"{key}.md").read_text(encoding="utf-8")
    html1 = (d1 / f"{key}.html").read_text(encoding="utf-8")
    text2 = (d2 / f"{key}.md").read_text(encoding="utf-8")
    html2 = (d2 / f"{key}.html").read_text(encoding="utf-8")
    url = json.loads((CRAWL / "state" / f"{key}.json").read_text(encoding="utf-8"))["url"]
    return Case("R1", "real", ChangeKind.STRUCTURE_CHANGED, text1, html1, text2, html2,
               note=f"{url}, crawled 11 Oct and 12 Oct 2026. Checked directly (not assumed): "
                    "the HTML genuinely gained tags between crawls (749 -> 777), so "
                    "STRUCTURE_CHANGED is the correct label, not CONTENT_CHANGED -- "
                    "an earlier draft of this case had the wrong expected label")


BASE_HTML = "<html><body><h1>Service</h1><p>FEE</p><ul><li>Document A</li></ul></body></html>"


def _cases() -> list[Case]:
    out = [_load_real_pair()]

    out.append(Case("C1", "constructed", ChangeKind.UNCHANGED,
                    "Fee: LKR 10,000. Documents: NIC, birth certificate.",
                    BASE_HTML,
                    "Fee: LKR 10,000. Documents: NIC, birth certificate.",
                    BASE_HTML,
                    note="identical page, re-fetched"))

    out.append(Case("C2", "constructed", ChangeKind.CONTENT_CHANGED,
                    "Fee: LKR 10,000. Documents: NIC, birth certificate.",
                    BASE_HTML,
                    "Fee: LKR 11,000. Documents: NIC, birth certificate.",
                    BASE_HTML,
                    note="single fee edit, same layout -- the proposal's named critical case"))

    out.append(Case("C3", "constructed", ChangeKind.STRUCTURE_CHANGED,
                    "Fee: LKR 10,000. Documents: NIC, birth certificate.",
                    BASE_HTML,
                    "Fee: LKR 10,000. Documents: NIC, birth certificate.",
                    "<html><body><h1>Service</h1><div><p>FEE</p></div><ul><li>Document A</li></ul></body></html>",
                    note="same words, page rebuilt with an added wrapper div"))

    out.append(Case("C4", "constructed", ChangeKind.UNCHANGED,
                    "Fee: LKR 10,000. Page visits: 184221. Last updated: 01/01/2026",
                    BASE_HTML,
                    "Fee: LKR 10,000. Page visits: 184399. Last updated: 02/01/2026",
                    BASE_HTML,
                    note="only a self-updating visit counter and a date stamp changed -- "
                         "the proposal's named noise case; a false positive here means "
                         "every page with a counter would burn tokens on every single run"))

    out.append(Case("C5", "constructed", ChangeKind.NEW, None, None,
                    "Fee: LKR 5,000.", BASE_HTML,
                    note="never seen before"))

    out.append(Case("C6", "constructed", ChangeKind.CONTENT_CHANGED,
                    "Documents required: NIC, birth certificate.",
                    BASE_HTML,
                    "Documents required: NIC, birth certificate, police report.",
                    BASE_HTML,
                    note="a document requirement added, no structural change"))

    out.append(Case("C7", "constructed", ChangeKind.UNCHANGED,
                    "Office hours: 8:30 AM to 4:15 PM. Contact: 011-2345678",
                    BASE_HTML,
                    "Office hours: 8:30 AM to 4:15 PM. Contact: 011-2345678",
                    BASE_HTML,
                    note="a bare clock time and a phone number present -- must NOT be "
                         "stripped as noise, since both are real citizen-facing information"))

    out.append(Case("C8", "constructed", ChangeKind.CONTENT_CHANGED,
                    "Fee: LKR 10,000.00. NIC number format: 123456789V",
                    BASE_HTML,
                    "Fee: LKR 10,500.00. NIC number format: 123456789V",
                    BASE_HTML,
                    note="an NIC-format example number is a stated identifier, not a "
                         "counter, and must not suppress the real fee change next to it"))
    return out


def main() -> None:
    cases = _cases()
    correct = 0
    print(f"{len(cases)} labelled cases ({sum(1 for c in cases if c.provenance=='real')} real, "
          f"{sum(1 for c in cases if c.provenance=='constructed')} constructed)\n")
    for c in cases:
        prev_fp = fingerprint(c.prev_text, c.prev_html) if c.prev_text is not None else None
        cur_fp = fingerprint(c.cur_text, c.cur_html)
        got = classify(prev_fp, cur_fp).kind
        ok = got == c.expected
        correct += ok
        print(f"{c.id:4} [{c.provenance:11}] expected={c.expected.value:17} got={got.value:17} "
              f"{'OK' if ok else 'WRONG'}")
        print(f"      {c.note}")
    print()
    print("=" * 70)
    print(f"Accuracy: {correct}/{len(cases)}  ({100*correct/len(cases):.0f}%)   target: 95%")
    false_positives = sum(1 for c in cases if c.expected == ChangeKind.UNCHANGED
                          and classify(fingerprint(c.prev_text, c.prev_html) if c.prev_text else None,
                                      fingerprint(c.cur_text, c.cur_html)).kind != ChangeKind.UNCHANGED)
    print(f"False positives on noise-only edits: {false_positives}   target: 0")


if __name__ == "__main__":
    main()
