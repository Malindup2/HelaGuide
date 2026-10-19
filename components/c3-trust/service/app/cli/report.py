"""
Turn the terminal demo into one readable HTML page for the panel.

    python -m app.cli.report                        run the whole demo, then write and open the page
    python -m app.cli.report --sqlite               the same without Docker
    python -m app.cli.report --from-file demo_output.txt
                                                    convert a saved demo output (no database, no model needed)
    python -m app.cli.report --out C:\\Users\\me\\Desktop\\report.html --no-open

The page has a heading and an explanation for each of the seven parts, real tables (candidate facts,
the confidence story, reputations, the formula checks), colour-coded percentages and warnings, the
audit trail, and the chart. It is one self-contained file: no internet, no scripts. The default
location is research/experiments/out/pp1_demo_report.html (git ignores that folder).
"""
import argparse
import contextlib
import html
import io
import json
import re
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from app.cli._common import add_common_args, utf8
from app.core.config import C3Settings

SEP_RE = re.compile(r"^-+(\s{2}-+)+\s*$")                    # the dashed line under a table header
BANNER_RE = re.compile(r"^(={20,}|-{20,})$")
CARD_RE = re.compile(r"^--- (\S+)\s+\((.*)\) ---$")           # --- ft-C1  (freetext, english) ---
STEP_RE = re.compile(r"^\[(\d+)\]\s+(\S+)\s+path=(\S+)\s+reporter=(\S+)")
KV_RE = re.compile(r"^(\s*)([A-Za-z][A-Za-z0-9_ /()-]{0,28}?)\s*:\s+(\S.*)$")
AUDIT_RE = re.compile(r"^\s{2,}(\S+) -> (\S+)\s{2,}(\S.*)$")
NOT_ROWS = ("decision:", "document check:", "only fact of its kind", "chart saved", "claims by different",
            "claims_disagree", "(in PP2", "OVERALL", "by style", "by path", "by split", "citizen now sees",
            "Audit trail", "[Press Enter", "Demo finished", "Stored fact")

EXPLAIN = {
    1: "C3 creates and owns a confidence record for every fact. The knowledge graph (C2) holds none.",
    2: "Each feedback message is matched to one stored fact: the service first, then the fact by meaning, kind of fact, "
       "variant and quoted value. When it cannot tell, it asks instead of guessing.",
    3: "Different citizens report the same passport fee. Every report is weighted by trust and independence, and "
       "confidence falls by a smaller amount each time until the fact is flagged.",
    4: "Citizens disagree with each other (1,500 against 2,000). The system records the disagreement and picks no winner.",
    5: "The official source changes a value. The new version starts again at 90%, and every earlier report is judged "
       "against the official value.",
    6: "What the interface receives: the agreed trust message, checked against the team's JSON schema, and the private explanation.",
    7: "Live checks that the formulas behave as claimed: calibrated, monotone, bounded, diminishing returns, copies discounted.",
}
CHIPS = {"yes": "ok", "PASS": "ok", "OK": "ok", "grounded": "ok", "support": "ok", "verified_by_source": "ok",
         "VERIFIED_BY_SOURCE": "ok", "active": "ok", "ok": "ok",
         "NO": "bad", "FAIL": "bad", "MISMATCH": "bad", "VERIFY_BEFORE_VISIT": "bad", "flagged": "bad",
         "contradicted_by_source": "bad",
         "LOW_CONFIDENCE": "warn", "disputed": "warn", "dispute": "warn", "clarification_needed": "warn",
         "NONE": "muted", "no_matching_fact": "muted"}
SCORE_COLS = {"score", "similarity", "T", "I", "kind", "variant", "value", "R after", "R before", "phrase similarity"}


# ------------------------------------------------------------------------------------------ reading
def read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):                 # saved by PowerShell's ">" (UTF-16)
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


# ------------------------------------------------------------------------------------------ parsing
def spans_of(sep: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(r"-+", sep)]


def split_row(line: str, spans: list[tuple[int, int]]) -> list[str]:
    cells = []
    for i, (start, _end) in enumerate(spans):
        stop = spans[i + 1][0] if i + 1 < len(spans) else None
        cells.append(line[start:stop].strip())
    return cells


def row_fits(line: str, spans: list[tuple[int, int]]) -> bool:
    if not line.strip() or BANNER_RE.match(line) or line.lstrip().startswith(NOT_ROWS):
        return False
    for i in range(len(spans) - 1):                          # the two spaces between columns must be blank
        gap = line[spans[i][1]:spans[i + 1][0]]
        if gap.strip():
            return False
    return True


def parse(text: str) -> list[dict]:
    """Return sections: {"title", "part", "blocks": [...]}. A block is a dict with a "type"."""
    lines = [ln.rstrip("\r") for ln in text.splitlines()]
    sections: list[dict] = [{"title": "Overview", "part": None, "blocks": []}]
    n, i = len(lines), 0

    def add(block: dict) -> None:
        sections[-1]["blocks"].append(block)

    while i < n:
        line = lines[i]
        if not line.strip() or line.startswith("[Press Enter") or "HF Hub" in line or line.startswith("Loading weights"):
            i += 1
            continue
        # banners: three lines (rule, title, rule)
        if BANNER_RE.match(line) and i + 2 < n and BANNER_RE.match(lines[i + 2]) and lines[i + 1].strip():
            title = lines[i + 1].strip()
            if line.startswith("="):
                m = re.match(r"PART (\d+)", title)
                sections.append({"title": title, "part": int(m.group(1)) if m else None, "blocks": []})
            else:
                add({"type": "heading", "text": title})
            i += 3
            continue
        # a table: a header line directly above a dashed line
        if i + 1 < n and SEP_RE.match(lines[i + 1]) and line.strip() and not BANNER_RE.match(line):
            spans = spans_of(lines[i + 1])
            headers = split_row(line, spans)
            rows, j = [], i + 2
            while j < n and row_fits(lines[j], spans):
                rows.append(split_row(lines[j], spans))
                j += 1
            add({"type": "table", "headers": headers, "rows": rows})
            i = j
            continue
        m = CARD_RE.match(line)
        if m:
            add({"type": "card", "kind": "message", "title": m.group(1), "meta": m.group(2)})
            i += 1
            continue
        m = STEP_RE.match(line)
        if m:
            add({"type": "card", "kind": "step", "title": f"{m.group(1)} · {m.group(2)}", "meta": f"{m.group(3)} · {m.group(4)}"})
            i += 1
            continue
        # JSON (one line, optionally followed by a note, or several lines)
        if line.lstrip().startswith("{"):
            obj, note, j = None, "", i
            try:
                obj, end = json.JSONDecoder().raw_decode(line.lstrip())
                note = line.lstrip()[end:].strip()
                j = i + 1
            except ValueError:
                buf = []
                for j in range(i, n):
                    buf.append(lines[j])
                    try:
                        obj = json.loads("\n".join(buf))
                        j += 1
                        break
                    except ValueError:
                        continue
                else:
                    obj = None
            if obj is not None:
                add({"type": "json", "data": obj, "note": note})
                i = j
                continue
        m = AUDIT_RE.match(line)
        if m:
            rows = []
            while i < n and AUDIT_RE.match(lines[i]):
                rows.append(list(AUDIT_RE.match(lines[i]).groups()))
                i += 1
            add({"type": "table", "headers": ["before", "after", "reason"], "rows": rows, "audit": True})
            continue
        if line.startswith("chart saved:"):
            add({"type": "chart", "path": line.split(":", 1)[1].strip()})
            i += 1
            continue
        m = KV_RE.match(line)
        if m:
            add({"type": "kv", "key": m.group(2).strip(), "value": m.group(3).strip(), "indent": len(m.group(1))})
            i += 1
            continue
        add({"type": "text", "text": line.strip()})
        i += 1
    return [s for s in sections if s["blocks"] or s["part"]]


# ------------------------------------------------------------------------------------------ rendering
def esc(s) -> str:
    return html.escape(str(s), quote=True)


def arrows(s: str) -> str:
    return esc(s).replace(" -&gt; ", " → ").replace("-&gt;", "→")


def pct_class(p: float) -> str:
    return "ok" if p >= 80 else "warn" if p >= 50 else "bad"


def cell_html(header: str, value: str) -> str:
    v = value.strip()
    if v in CHIPS:
        return f'<span class="chip {CHIPS[v]}">{esc(v)}</span>'
    if re.fullmatch(r"\d+(\.\d+)?%", v):
        return f'<span class="chip {pct_class(float(v[:-1]))}">{esc(v)}</span>'
    if header in SCORE_COLS:
        try:
            f = float(v)
            if 0 <= f <= 1:
                return f'<div class="meter"><i style="width:{f * 100:.0f}%"></i></div><span class="num">{esc(v)}</span>'
        except ValueError:
            pass
    return arrows(v)


def table_html(b: dict, caption: str | None) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in b["headers"])
    best = b["headers"] and b["headers"][0].startswith("candidate")
    body = ""
    heads = b["headers"]
    for idx, r in enumerate(b["rows"]):
        cls = ' class="best"' if best and idx == 0 else ""
        cells = []
        for h, c in zip(heads, r):
            if h == "confidence" and "warning" in heads and re.fullmatch(r"\d+%", c.strip()):
                code = r[heads.index("warning")].strip()               # colour the percentage like the console does
                tone = {"NONE": "ok", "LOW_CONFIDENCE": "warn", "VERIFY_BEFORE_VISIT": "bad", "VERIFIED_BY_SOURCE": "ok"}.get(code, pct_class(float(c.strip()[:-1])))
                cells.append(f'<td><span class="chip {tone}">{esc(c.strip())}</span></td>')
            else:
                cells.append(f"<td>{cell_html(h, c)}</td>")
        body += f"<tr{cls}>" + "".join(cells) + "</tr>"
    cap = f'<div class="cap">{esc(caption.rstrip(":"))}</div>' if caption else ""
    return f'{cap}<div class="tablewrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def kv_html(b: dict) -> str:
    k, v = b["key"], b["value"]
    if k == "decision":
        m = re.match(r"(.*?)\s*\|\s*expected:\s*(.*?)\s+(OK|MISMATCH)\s*$", v)
        if m:
            return (f'<div class="decision {CHIPS[m.group(3)]}"><b>Decision</b> {arrows(m.group(1))}'
                    f'<span class="exp">expected: {arrows(m.group(2))}</span><span class="chip {CHIPS[m.group(3)]}">{m.group(3)}</span></div>')
        return f'<div class="decision"><b>Decision</b> {arrows(v)}</div>'
    if k == "citizen sees":
        m = re.match(r"(\d+)%\s*\|\s*(.*)", v)
        if m:
            tone = "bad" if "STRONG WARNING" in m.group(2) else "warn" if "WARNING" in m.group(2) else "ok"
            return (f'<div class="sees"><b>The citizen sees</b><span class="chip {tone} big">{m.group(1)}%</span>'
                    f'<span>{arrows(m.group(2))}</span></div>')
    cls = " strong" if k in ("message", "English") else ""
    return f'<div class="kv{cls}"><span class="k">{esc(k)}</span><span class="v">{arrows(v)}</span></div>'


def json_html(b: dict) -> str:
    note = ""
    if "valid against" in b["note"]:
        note = f'<span class="chip ok">schema valid</span> <span class="muted">{esc(b["note"].strip("[]"))}</span>'
    return f'<div class="json"><pre>{esc(json.dumps(b["data"], indent=2, ensure_ascii=False))}</pre>{note}</div>'


def kpis(text: str, sections: list[dict]) -> list[tuple[str, str, str]]:
    out = []
    m = re.search(r"registered\s*:\s*(\d+) facts across (\d+) services, (\d+) reporters", text)
    if m:
        out.append((m.group(1), "facts, each with a confidence record", f"{m.group(2)} services · {m.group(3)} demo citizens"))
    m = re.search(r"OVERALL:\s*(\d+)/(\d+) correct", text)
    if m:
        out.append((f"{m.group(1)}/{m.group(2)}", "messages grounded correctly", "mock labelled set (English, Sinhala, Singlish)"))
    for s in sections:
        for b in s["blocks"]:
            if b["type"] == "table" and "confidence" in b["headers"] and "warning" in b["headers"] and b["rows"]:
                last = b["rows"][-1][b["headers"].index("confidence")]
                first = re.search(r"Starting confidence (\d+)%", text)
                out.append((f"{first.group(1) if first else '90'}% → {last}", "passport fee after six reports", "the story of Part 3"))
                break
        else:
            continue
        break
    m = re.search(r"(\d+)/(\d+) checks passed", text)
    if m:
        out.append((f"{m.group(1)}/{m.group(2)}", "formula checks passed", "calibration, bounds, diminishing returns"))
    m = re.search(r"embedding model\s*:\s*(\S+)", text)
    if m:
        out.append((m.group(1).split("/")[-1], "sentence-embedding model", "pretrained, inference only"))
    return out


CSS = """
:root{--black:#0d0d0d;--ink:#1c1c1c;--muted:#6b7280;--line:#e5e7eb;--soft:#f6f6f7;--orange:#f26a1b;--orange-bg:#fff3ea;
--green:#15803d;--green-bg:#e8f6ee;--amber:#a15c00;--amber-bg:#fff4dc;--red:#b42318;--red-bg:#fdeceb}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--soft);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,"Nirmala UI","Noto Sans Sinhala","Iskoola Pota",sans-serif}
header{background:var(--black);color:#fff;padding:0 28px;height:62px;display:flex;align-items:center;gap:14px}
.mark{width:30px;height:30px;border-radius:7px;background:var(--orange);color:#111;display:grid;place-items:center;font-weight:800}
header b{font-size:20px}header .d{color:#9ca3af;font-size:14px}header .r{margin-left:auto;color:#d1d5db;font-size:12px;border:1px solid #3a3a3a;border-radius:999px;padding:4px 12px}
.wrap{display:grid;grid-template-columns:230px minmax(0,1fr);gap:26px;max-width:1380px;margin:22px auto;padding:0 22px}
nav{position:sticky;top:16px;align-self:start;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px}
nav h4{margin:0 0 8px;font-size:12px;letter-spacing:.5px;text-transform:uppercase;color:var(--muted)}
nav a{display:block;padding:6px 8px;border-radius:6px;color:var(--ink);text-decoration:none;font-size:13.5px}nav a:hover{background:var(--orange-bg)}
main{min-width:0}
.intro{background:#fff;border:1px solid var(--line);border-left:4px solid var(--orange);border-radius:12px;padding:14px 18px;margin-bottom:18px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:22px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi .n{font-size:26px;font-weight:800;line-height:1.1}.kpi .l{font-weight:600;margin-top:4px}.kpi .s{color:var(--muted);font-size:12.5px}
section{background:#fff;border:1px solid var(--line);border-radius:14px;margin-bottom:24px;overflow:hidden}
section>h2{margin:0;padding:16px 22px;background:var(--black);color:#fff;font-size:19px;display:flex;gap:12px;align-items:center}
section>h2 .p{background:var(--orange);color:#111;border-radius:6px;padding:1px 9px;font-size:14px;font-weight:800}
.explain{padding:12px 22px;background:#fafafa;border-bottom:1px solid var(--line);color:#374151}
.body{padding:18px 22px}
h3{margin:22px 0 8px;font-size:16px;padding-bottom:5px;border-bottom:2px solid var(--orange);display:inline-block}
.cap{margin:12px 0 6px;font-weight:600}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;margin:6px 0 12px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{background:#fafafa;text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);color:#374151;white-space:nowrap}
td{padding:7px 12px;border-bottom:1px solid #f0f0f0;vertical-align:middle}
tr:last-child td{border-bottom:0}tr.best td{background:var(--orange-bg);font-weight:600}
.chip{display:inline-block;padding:1px 10px;border-radius:999px;font-weight:700;font-size:12.5px;border:1px solid}
.chip.ok{color:var(--green);background:var(--green-bg);border-color:#bfe3cc}.chip.warn{color:var(--amber);background:var(--amber-bg);border-color:#f3d89b}
.chip.bad{color:var(--red);background:var(--red-bg);border-color:#f3b8b3}.chip.muted{color:var(--muted);background:#f3f4f6;border-color:var(--line)}
.chip.big{font-size:20px;padding:2px 14px}
.meter{display:inline-block;width:70px;height:7px;background:#eee;border-radius:4px;overflow:hidden;vertical-align:middle;margin-right:8px}
.meter i{display:block;height:100%;background:var(--black)}.num{font-variant-numeric:tabular-nums}
.card{border:1px solid var(--line);border-radius:12px;margin:14px 0;overflow:hidden}
.card>.ch{background:#fafafa;padding:8px 14px;border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center;font-weight:700}
.card>.ch .meta{color:var(--muted);font-weight:400;font-size:13px}.card>.cb{padding:8px 14px}
.kv{display:grid;grid-template-columns:150px 1fr;gap:10px;padding:3px 0}.kv .k{color:var(--muted);font-size:13px}.kv.strong .v{font-weight:600}
.decision{margin:8px 0 4px;padding:8px 12px;border-radius:8px;background:var(--soft);display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.decision.ok{background:var(--green-bg)}.decision.bad{background:var(--red-bg)}.decision .exp{color:var(--muted);font-size:13px}
.sees{margin:8px 0 2px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
pre{margin:0;white-space:pre-wrap;font:12.5px/1.5 ui-monospace,Consolas,monospace}
.json{background:#111;color:#e5e7eb;border-radius:10px;padding:12px 14px;margin:10px 0}.json .muted{color:#9ca3af}
.json .chip{margin-top:8px}.muted{color:var(--muted)}p{margin:8px 0}
.chart{border:1px solid var(--line);border-radius:12px;padding:10px;margin:12px 0;background:#fff}.chart svg{max-width:100%;height:auto}
footer{color:var(--muted);font-size:12.5px;text-align:center;padding:6px 0 30px}
@media(max-width:900px){.wrap{grid-template-columns:1fr}nav{position:static}.kv{grid-template-columns:1fr}}
@media print{nav{display:none}.wrap{display:block}section{break-inside:avoid-page}header{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""


def render(sections: list[dict], text: str, source: str, out_dir: Path | None = None) -> str:
    nav = "".join(f'<a href="#s{i}">{esc(s["title"])}</a>' for i, s in enumerate(sections))
    cards = "".join(f'<div class="kpi"><div class="n">{esc(n)}</div><div class="l">{esc(l)}</div><div class="s">{esc(s)}</div></div>'
                    for n, l, s in kpis(text, sections))
    parts = []
    for i, sec in enumerate(sections):
        m = re.match(r"PART (\d+) · (.*)", sec["title"])
        head = (f'<span class="p">PART {m.group(1)}</span>{esc(m.group(2))}' if m else esc(sec["title"]))
        expl = f'<div class="explain">{esc(EXPLAIN[sec["part"]])}</div>' if sec["part"] in EXPLAIN else ""
        out, blocks, k, open_card = [], sec["blocks"], 0, False
        while k < len(blocks):
            b = blocks[k]
            t = b["type"]
            if t == "card":
                if open_card:
                    out.append("</div></div>")
                out.append(f'<div class="card"><div class="ch">{esc(b["title"])}<span class="meta">{esc(b["meta"])}</span></div><div class="cb">')
                open_card = True
            elif t == "heading":
                if open_card:
                    out.append("</div></div>")
                    open_card = False
                out.append(f'<h3>{esc(b["text"])}</h3>')
            elif t == "table":
                cap = None
                if out and k > 0 and blocks[k - 1]["type"] == "text" and blocks[k - 1]["text"].endswith(":"):
                    cap = blocks[k - 1]["text"]
                    out.pop()
                out.append(table_html(b, cap))
            elif t == "kv":
                out.append(kv_html(b))
            elif t == "json":
                out.append(json_html(b))
            elif t == "chart":
                svg = ""
                for cand in (Path(b["path"]), (out_dir / Path(b["path"]).name) if out_dir else None):
                    if cand and cand.is_file() and cand.suffix.lower() == ".svg":
                        svg = cand.read_text(encoding="utf-8", errors="replace")
                        svg = svg[svg.find("<svg"):] if "<svg" in svg else ""
                        break
                out.append(f'<div class="chart">{svg}</div>' if svg else "")
            else:
                txt = b["text"]
                if k + 1 < len(blocks) and blocks[k + 1]["type"] == "table" and txt.endswith(":"):
                    pass                                                    # becomes the table's caption
                out.append(f"<p>{arrows(txt)}</p>")
            k += 1
        if open_card:
            out.append("</div></div>")
        parts.append(f'<section id="s{i}"><h2>{head}</h2>{expl}<div class="body">{"".join(out)}</div></section>')
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>HelaGuide · Component 3 · PP1 demo report</title><style>{CSS}</style></head><body>"
            f'<header><span class="mark">H</span><b>HelaGuide</b><span class="d">helaguide.lk</span>'
            f'<span class="r">Component 3 · PP1 demo report · mock data</span></header>'
            f'<div class="wrap"><nav><h4>Contents</h4>{nav}</nav><main>'
            f'<div class="intro"><b>Civic Trust and Knowledge Verification Engine.</b> Every number below was calculated by the '
            f"algorithms when the demo ran, from mock data (the knowledge graph, the citizens and the messages are mock). "
            f"Confidence is shown as a percentage: how far citizens' experience supports a published fact.</div>"
            f'<div class="kpis">{cards}</div>{"".join(parts)}</main></div>'
            f"<footer>Generated {stamp} from {esc(source)}</footer></body></html>")


# ------------------------------------------------------------------------------------------ command
def main(argv=None) -> None:
    utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--from-file", help="convert a saved demo output instead of running the demo")
    ap.add_argument("--out", help="where to write the page (default: research/experiments/out/pp1_demo_report.html)")
    ap.add_argument("--no-open", action="store_true", help="do not open the page in the browser")
    args = ap.parse_args(argv)
    settings = C3Settings()
    if args.from_file:
        text, source = read_text(Path(args.from_file)), Path(args.from_file).name
    else:
        from app.cli import demo
        demo_args = (["--sqlite"] if args.sqlite else []) + (["--db", args.db] if args.db else []) \
            + (["--embedding", args.embedding] if args.embedding else [])
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                demo.main(demo_args)
        except SystemExit as exc:                                   # e.g. the database is not running
            sys.stdout.write(buf.getvalue())
            sys.exit(exc.code)
        text, source = buf.getvalue(), "a live run of python -m app.cli.demo"
    sections = parse(text)
    if not any(s["part"] for s in sections):
        print("No demo output found in that input (expected the 'PART 1 ...' banners).")
        sys.exit(1)
    out = Path(args.out) if args.out else settings.out_dir / "pp1_demo_report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(sections, text, source, settings.out_dir), encoding="utf-8")
    print(f"report written: {out}")
    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
