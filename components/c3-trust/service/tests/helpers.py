"""Settings used by the tests: in-memory SQLite and the tiny stand-in embedder (no download, no key)."""
from app.core.config import C3Settings


def make_settings(**over) -> C3Settings:
    base = dict(_env_file=None, database_url="sqlite://", embedding_backend="hash",
                tau_miss_cos=0.15, tau_f=0.42, delta_f=0.05)
    base.update(over)
    return C3Settings(**base)
