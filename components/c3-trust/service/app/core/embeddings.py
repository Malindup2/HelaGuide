"""
Sentence embeddings. Two interchangeable backends:

  sbert : the real pretrained model (sentence-transformers). Inference only, no training.
          Downloaded once from Hugging Face into your user cache folder, outside the repo.
  hash  : a tiny deterministic stand-in (feature hashing of words). It needs no download and
          is used by the unit tests and by --embedding hash plumbing checks. It is NOT a
          semantic model: it only matches shared words.

Vectors are L2-normalised, so cosine similarity is a plain dot product.
"""
from __future__ import annotations

import hashlib
import re
import threading
from typing import Protocol

import numpy as np

from app.core.config import C3Settings


class Embedder(Protocol):
    name: str

    def encode(self, texts: list[str]) -> np.ndarray: ...


class HashEmbedder:
    name = "hash-256"

    def __init__(self, dim: int = 256):
        self.dim = dim

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            words = re.findall(r"[a-z0-9]+", (t or "").lower())
            feats = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
            for f in feats:
                h = int(hashlib.md5(f.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0 if (h >> 64) % 2 == 0 else -1.0
            n = np.linalg.norm(out[i])
            if n > 0:
                out[i] /= n
        return out


class SbertEmbedder:
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on the user's install
            raise RuntimeError(
                "sentence-transformers is not installed. Run:  pip install -e \".[research]\"") from exc
        self.name = model_name
        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._model.encode(list(texts), normalize_embeddings=True,
                                              show_progress_bar=False), dtype=np.float32)


class CachingEmbedder:
    """Remembers every text it has embedded, so repeated runs and tuning sweeps stay fast."""

    def __init__(self, inner: Embedder):
        self.inner = inner
        self.name = inner.name
        self._memo: dict[str, np.ndarray] = {}

    def encode(self, texts: list[str]) -> np.ndarray:
        missing = [t for t in dict.fromkeys(texts) if t not in self._memo]
        if missing:
            for t, v in zip(missing, self.inner.encode(missing)):
                self._memo[t] = v
        return np.stack([self._memo[t] for t in texts]) if texts else np.zeros((0, 1), dtype=np.float32)


_cache: dict[tuple[str, str], Embedder] = {}
_lock = threading.Lock()


def get_embedder(settings: C3Settings) -> Embedder:
    key = (settings.embedding_backend, settings.embedding_model)
    with _lock:
        if key not in _cache:
            inner = HashEmbedder() if settings.embedding_backend == "hash" \
                else SbertEmbedder(settings.embedding_model)
            _cache[key] = CachingEmbedder(inner)
        return _cache[key]


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
