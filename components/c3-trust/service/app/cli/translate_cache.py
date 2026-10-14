"""
Fill / refresh the translation cache with Gemini, once, before the demo.

    python -m app.cli.translate_cache --dry-run       show what would be translated, send nothing
    python -m app.cli.translate_cache --overwrite     replace the saved (authored) translations with Gemini's
    python -m app.cli.translate_cache                 translate only messages that are not in the cache at all
    python -m app.cli.translate_cache --compare       translate, show next to the saved text, SAVE NOTHING (uses quota)

It is safe to stop and run again:
  * every translation is saved the moment it succeeds;
  * --overwrite skips messages Gemini has already translated, so a second run only does what is left;
  * if Google says "too many requests" it stops, tells you how long to wait, and keeps everything done so far.

Useful options:  --limit 6  (translate at most 6 now)    --pause 10  (seconds between calls, default 7)
                 --again    (redo even messages Gemini already translated)

The free tier allows only a few requests per minute (about 10 for gemini-2.5-flash; check your own limits in
Google AI Studio). The default pause of 7 seconds stays under that.

The cache starts with translations written by the project author (source "authored"). After --overwrite the
entries say source "gemini", reviewed false, and keep the old wording in "previous_text_en". Read every
translation, fix mistakes by hand in normalised_cache.json and set "reviewed": true.
"""
import argparse
import json
import time

from app.cli._common import banner, table, utf8
from app.core.config import C3Settings
from app.core.lexicon import needs_translation
from app.core.normaliser import Normaliser, QuotaExhausted, RateLimited, TranslationError
from app.core.util import text_hash

SLEEP = time.sleep        # tests replace this so they do not really wait


def collect(data_dir) -> list[tuple[str, str, str | None]]:
    out = []
    ft = json.loads((data_dir / "feedback_freetext.json").read_text(encoding="utf-8"))["messages"]
    st = json.loads((data_dir / "feedback_structured.json").read_text(encoding="utf-8"))["messages"]
    for m in ft:
        if not m.get("text_en") and needs_translation(m.get("language"), m["raw_text"]):
            out.append((m["message_id"], m["raw_text"], m.get("language")))
    for m in st:
        if needs_translation(None, m["text"]):
            out.append((m["feedback_id"], m["text"], None))
    return out


def select(todo, cache: dict, args):
    """Which messages still need Gemini?"""
    def entry(raw):
        return cache.get(text_hash(raw), {})
    if args.again or args.compare:
        return list(todo)
    if args.overwrite:
        return [t for t in todo if entry(t[1]).get("source") != "gemini"]
    return [t for t in todo if text_hash(t[1]) not in cache]


def main(argv=None) -> None:
    utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--again", action="store_true", help="redo messages Gemini has already translated")
    ap.add_argument("--limit", type=int, help="translate at most this many messages in this run")
    ap.add_argument("--pause", type=float, default=7.0, help="seconds between requests (default 7)")
    args = ap.parse_args(argv)
    s = C3Settings()
    norm = Normaliser(s)
    everything = collect(s.data_dir)
    todo = select(everything, norm.cache, args)
    done_already = len(everything) - len(todo)
    if args.limit is not None:
        todo = todo[: max(args.limit, 0)]
    banner(f"{len(todo)} message(s) to translate now, {done_already} already done or not needed (model {s.gemini_model})")
    if args.dry_run:
        for mid, raw, _ in todo:
            print(f"  {mid}: {raw}")
        return
    if not todo:
        print("Nothing to do. (Use --overwrite to replace authored translations, --again to redo Gemini's.)")
        return
    if not s.gemini_api_key:
        print("No key found. Put  C3_GEMINI_API_KEY=...  in service/.env")
        return
    client = norm.client()
    rows, ok, failed, stop_reason = [], 0, [], None
    for i, (mid, raw, _) in enumerate(todo, 1):
        try:
            en = client.translate(raw)
        except QuotaExhausted as exc:
            stop_reason = f"STOPPED: {exc}"
            break
        except RateLimited as exc:
            wait = f" Google suggests waiting about {int(exc.retry_after) + 1} seconds." if exc.retry_after else " Wait a minute."
            stop_reason = f"STOPPED: Gemini says too many requests per minute.{wait}"
            break
        except TranslationError as exc:
            print(f"  [{i}/{len(todo)}] {mid}: FAILED ({exc})")
            failed.append(mid)
            SLEEP(args.pause)
            continue
        old = norm.cache.get(text_hash(raw), {}).get("text_en", "")
        rows.append([mid, "same" if old.strip().lower() == en.strip().lower() else "DIFFERENT", old, en])
        print(f"  [{i}/{len(todo)}] {mid}: ok")
        ok += 1
        if not args.compare:
            norm.put(raw, en, "gemini", s.gemini_model, reviewed=False)
            if old:
                norm.cache[text_hash(raw)]["previous_text_en"] = old
            norm.save()                                     # saved immediately: safe to stop at any time
        if i < len(todo):
            SLEEP(args.pause)
    if rows:
        print("\n" + table(["message", "vs saved", "saved translation", "gemini translation"], rows, max_width=52))
    print()
    if args.compare:
        print("--compare: nothing was saved.")
    elif ok:
        print(f"saved {ok} translation(s) to {norm.cache_path}. REVIEW them before the demo.")
    if failed:
        print(f"{len(failed)} failed for other reasons (often a temporary Google overload, HTTP 503): {', '.join(failed)}")
        print("The old translations were kept for those. Run the same command again to retry them.")
    if stop_reason:
        print(stop_reason)
        print("Everything translated so far is saved. Run the SAME command again later to continue.")
    elif not failed and ok:
        print("All done. You can run it again any time: it only does what is left.")


if __name__ == "__main__":
    main()
