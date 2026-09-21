"""Validate every contracts/examples/*.example.json against its schema. Run by CI."""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1] / "contracts"


def main() -> int:
    failures = 0
    for example in sorted((ROOT / "examples").glob("*.example.json")):
        name = example.name.removesuffix(".example.json")
        schema_path = ROOT / "schema" / "v1" / f"{name}.schema.json"
        if not schema_path.exists():
            print(f"FAIL  {name}: no schema at {schema_path.relative_to(ROOT.parent)}")
            failures += 1
            continue
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker())
                        .iter_errors(json.loads(example.read_text(encoding="utf-8"))),
                        key=lambda e: list(e.path))
        if errors:
            failures += 1
            print(f"FAIL  {name}")
            for e in errors:
                print(f"      {'/'.join(map(str, e.path)) or '<root>'}: {e.message}")
        else:
            print(f"ok    {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
