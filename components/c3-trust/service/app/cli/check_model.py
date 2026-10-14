"""Check that the pretrained embedding model loads and behaves sensibly.

    python -m app.cli.check_model
"""
import argparse
import time

import numpy as np

from app.cli._common import add_common_args, banner, settings_from_args, table, utf8
from app.core.embeddings import get_embedder

PAIRS = [
    ("They charged me 12,000 for the passport.", "Passport: normal fee is LKR 11,000", "should be HIGH"),
    ("They charged me 12,000 for the passport.", "Death Certificate: required document - Medical certificate", "should be LOW"),
    ("The one day NIC service cost 3,500.", "National Identity Card (NIC): one day fee is LKR 2,500", "should be HIGH"),
    ("The one day NIC service cost 3,500.", "National Identity Card (NIC): first issue fee is LKR 0", "should be LOWER"),
]


def main(argv=None) -> None:
    utf8()
    ap = argparse.ArgumentParser(description=__doc__)
    add_common_args(ap)
    args = ap.parse_args(argv)
    s = settings_from_args(args)
    banner(f"Loading embedding model: {s.embedding_backend} / {s.embedding_model}")
    t0 = time.time()
    emb = get_embedder(s)
    print(f"loaded in {time.time() - t0:.1f}s  ({emb.name})")
    rows, sims = [], []
    for a, b, note in PAIRS:
        va, vb = emb.encode([a])[0], emb.encode([b])[0]
        sim = float(np.dot(va, vb))
        sims.append(sim)
        rows.append([f"{sim:.3f}", a, b, note])
    print(table(["similarity", "message", "fact description", "expectation"], rows, max_width=58))
    good = sims[0] > sims[1] and sims[2] > sims[3]
    print("\nRESULT:", "OK, related texts score higher than unrelated ones." if good else
          "CHECK THIS: related texts did not score higher. With --embedding hash this is expected.")
    t0 = time.time()
    emb.encode(["speed test sentence"] * 8)
    print(f"speed: 8 sentences in {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()
