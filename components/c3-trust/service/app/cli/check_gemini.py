"""Check that your Gemini key works and translate three sample messages.

    python -m app.cli.check_gemini              (translate 3 samples)
    python -m app.cli.check_gemini --models     (list the models your key can use)
"""
import argparse

from app.cli._common import utf8
from app.core.config import C3Settings
from app.core.normaliser import GeminiClient, TranslationError

SAMPLES = [
    "passport eke normal fee eka 12000 kiyala kiwwa, oyala kiwwe 11000 kiyala",
    "ගමන් බලපත්‍රයේ සාමාන්‍ය ගාස්තුව රුපියල් 11,000ක් ලෙසම අය කළා, ඒක හරි.",
    "birth certificate eka ganna hospital eken letter ekak ayeth ilwwa",
]


def main(argv=None) -> None:
    utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", action="store_true", help="list models that support generateContent")
    ap.add_argument("--model", help="model name to test (default: C3_GEMINI_MODEL)")
    args = ap.parse_args(argv)
    s = C3Settings()
    if not s.gemini_api_key:
        print("No key found. Put  C3_GEMINI_API_KEY=...  in service/.env  (that file is ignored by git).")
        return
    client = GeminiClient(s.gemini_api_key, args.model or s.gemini_model, pause=s.llm_pause_seconds)
    try:
        if args.models:
            for name in client.list_models():
                print(name)
            return
        print(f"model: {client.model}\n")
        for raw in SAMPLES:
            print("raw :", raw)
            print("en  :", client.translate(raw), "\n")
        print("RESULT: OK, Gemini translation works.")
    except TranslationError as exc:
        print("PROBLEM:", exc)
        print("If the model name is wrong, run:  python -m app.cli.check_gemini --models   and set C3_GEMINI_MODEL.")


if __name__ == "__main__":
    main()
