"""Local explicit source-review/publication tooling. Never auto-reviews generated text."""
import argparse
import json
from pathlib import Path
from app.guidance.content import GuidanceContent
from app.guidance.registry import ContentRegistry
from app.guidance.sources import ProcedureSource


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "review", "publish"))
    parser.add_argument("--directory", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--source-job")
    parser.add_argument("--reviewed-content")
    parser.add_argument("--reviewer")
    parser.add_argument("--kind", choices=("human_source_fidelity", "internal_fictional_author"))
    parser.add_argument("--confirm-source-review", action="store_true")
    args = parser.parse_args()
    store = ContentRegistry(args.directory)
    if args.command == "inspect":
        artifact = store.inspect(args.artifact)
        artifact["content"] = artifact["content"].model_dump(mode="json")
        print(json.dumps(artifact, indent=2))
        return
    if not args.source_job:
        parser.error("review/publication require the exact source-job snapshot")
    payload = json.loads(Path(args.source_job).read_text(encoding="utf-8"))
    source = ProcedureSource.model_validate_json(json.dumps(payload["source"]))
    source.validate()
    if args.command == "review":
        if not all((args.reviewed_content, args.reviewer, args.kind, args.confirm_source_review)):
            parser.error("explicit reviewer, kind, confirmation and statement-level reviewed-content JSON required")
        content = GuidanceContent.model_validate_json(Path(args.reviewed_content).read_text(encoding="utf-8"))
        if not content.review or content.review.reviewer != args.reviewer:
            raise ValueError("review identity does not match the supplied source-review record")
        print(store.review(source, args.artifact, content, kind=args.kind))
    else:
        print(store.publish(source, args.artifact))


if __name__ == "__main__":
    main()
