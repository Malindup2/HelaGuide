"""Local operator tooling; no provider calls, policy changes or HTTP routes.

Run from service/: python -m app.preparation.content_cli --help
"""

import argparse
import os
from pathlib import Path

from app.preparation.explanation_store import ArtifactStoreError, ExplanationArtifactStore
from app.preparation.explanations import (
    ExplanationService, OutputRejected, validate_stored_artifact,
)


def default_directory() -> Path:
    from dotenv import load_dotenv

    service = Path(__file__).resolve().parents[2]
    load_dotenv(service / ".env", override=False)
    return Path(os.getenv("C4_CONTENT_DIR") or service / ".local" / "wording-artifacts")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List stored packages and actual review state")
    show = commands.add_parser("show", help="Show exact wording, source packet and provenance")
    show.add_argument("key")
    review = commands.add_parser("review", help="Record a human's completed source review")
    review.add_argument("key")
    review.add_argument("--reviewer", required=True, help="Non-personal reviewer reference")
    review.add_argument(
        "--confirm-source-check", action="store_true", required=True,
        help="Attest that you checked every explanation against its supplied sources",
    )
    args = parser.parse_args(argv)
    store = ExplanationArtifactStore(args.directory or default_directory())
    try:
        if args.command == "list":
            keys = store.keys()
            if not keys:
                print("No prepared artifacts. Guidance will use source fallback on a cache miss.")
            for key in keys:
                try:
                    stored = store.read(key)
                    if stored is None:
                        continue
                    validate_stored_artifact(stored)
                    artifact = stored.artifact
                    status = "reviewed" if artifact.review is not None else "pending_review"
                    print(f"{key}  {status}  provider={artifact.provider.name} "
                          f"model={artifact.provider.requested_model}")
                except (ArtifactStoreError, OutputRejected):
                    print(f"{key}  invalid_or_incompatible")
            return 0
        stored = store.read(args.key)
        if stored is None:
            raise ArtifactStoreError("artifact_not_found")
        validate_stored_artifact(stored)
        if args.command == "show":
            print(stored.model_dump_json(indent=2))
        else:
            # mark_reviewed uses only the store; no provider is instantiated.
            service = ExplanationService(None, artifact_store=store, generation_enabled=False)
            artifact = service.mark_reviewed(args.key, reviewer_reference=args.reviewer)
            print(f"Reviewed {args.key}; provider={artifact.provider.name}; "
                  f"digest={artifact.review.artifact_digest}")
        return 0
    except (ArtifactStoreError, OutputRejected, ValueError) as exc:
        print(f"Artifact operation rejected: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
