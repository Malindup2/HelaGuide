"""File-backed state for stage 1: the latest fingerprint per URL, plus an archive of raw pages.

Layout under the root directory:

    state/<url-hash>.json                latest fingerprint and metadata, used to classify the next run
    archive/<YYYY-MM-DD>/<url-hash>.html raw page, kept for extraction and for audit
    archive/<YYYY-MM-DD>/<url-hash>.md   extracted text (Markdown)

Nothing here is committed to git: crawls are data, and data stays out of the repository.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.core.acquisition.fingerprint import Fingerprint, sha256


def url_key(url: str) -> str:
    return sha256(url)[:16]


@dataclass
class Snapshot:
    url: str
    fingerprint: Fingerprint
    fetched_at: str
    status: int | None
    tls_relaxed: bool


class SnapshotStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.state_dir = self.root / "state"
        self.archive_dir = self.root / "archive"

    def latest(self, url: str) -> Snapshot | None:
        path = self.state_dir / f"{url_key(url)}.json"
        if not path.exists():
            return None
        d = json.loads(path.read_text(encoding="utf-8"))
        return Snapshot(d["url"], Fingerprint.from_dict(d["fingerprint"]), d["fetched_at"],
                        d.get("status"), bool(d.get("tls_relaxed", False)))

    def save(self, snap: Snapshot, html: str, text: str, archive: bool = True) -> None:
        """Record the latest fingerprint; archive the raw page only when asked.

        An UNCHANGED page updates its state (so freshness is known) but is not archived
        again: there is nothing new to keep.
        """
        self.state_dir.mkdir(parents=True, exist_ok=True)
        key = url_key(snap.url)
        (self.state_dir / f"{key}.json").write_text(
            json.dumps({
                "url": snap.url,
                "fingerprint": snap.fingerprint.to_dict(),
                "fetched_at": snap.fetched_at,
                "status": snap.status,
                "tls_relaxed": snap.tls_relaxed,
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        if not archive:
            return
        day_dir = self.archive_dir / snap.fetched_at[:10]
        day_dir.mkdir(parents=True, exist_ok=True)
        (day_dir / f"{key}.html").write_text(html, encoding="utf-8")
        (day_dir / f"{key}.md").write_text(text, encoding="utf-8")
