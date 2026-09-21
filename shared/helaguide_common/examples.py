"""Load the canned samples from contracts/examples. Used in stub mode and in tests."""
import json
from functools import lru_cache
from pathlib import Path

from .config import get_settings


@lru_cache
def load_example(name: str, contracts_dir: str | None = None) -> dict:
    base = Path(contracts_dir) if contracts_dir else get_settings().contracts_dir
    path = base / "examples" / f"{name}.example.json"
    return json.loads(path.read_text(encoding="utf-8"))
