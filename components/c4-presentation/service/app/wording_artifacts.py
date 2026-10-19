"""Operator CLI for reusable wording. No changes to sessions or policy state."""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from app.core.demo_procedures import FIXTURES_ROOT, SCENARIOS
from app.core.explanation_store import MAX_ARTIFACT_BYTES, ArtifactStoreError, parse_artifact_json
from app.core.explanations import OutputRejected, _canonical
from app.core.llm_provider import OpenAIExplanationProvider, ProviderFailure
from app.core.prepared_wording import prepare_wording_packet, wording_key
from app.core.procedure_graph import build_procedure_graph
from app.core.procedure_input import load_procedure_input
from app.core.wording_service import (
    PreparedWordingStore, generate_wording, human_template, make_human_artifact,
    preparation_batches, resolve_wording,
)
from app.models.prepared_wording import HumanWordingSubmission


def add_source_arguments(parser):
    parser.add_argument("--scenario", choices=SCENARIOS)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--enrichment", type=Path)
    parser.add_argument("--style", choices=("plain", "extra_plain", "concise"), default="plain")


def load_source(args):
    if args.scenario:
        if args.plan is not None or args.enrichment is not None:
            raise ValueError("choose scenario OR plan/enrichment")
        base = FIXTURES_ROOT / args.scenario
        plan, enrichment = base / "plan.json", base / "enrichment.json"
    else:
        if args.plan is None or args.enrichment is None:
            raise ValueError("supply --scenario or both --plan and --enrichment")
        plan, enrichment = args.plan, args.enrichment
    return build_procedure_graph(load_procedure_input(plan, enrichment))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List actual stored origin and review status")
    for name in ("plan", "template", "validate-human", "import-human", "generate", "resolve"):
        command = commands.add_parser(name)
        add_source_arguments(command)
        if name == "template":
            command.add_argument("--author", required=True)
            command.add_argument("--output", type=Path, required=True)
        if name in ("validate-human", "import-human"):
            command.add_argument("--input", type=Path, required=True)
            command.add_argument("--allow-partial", action="store_true")
        if name in ("import-human", "generate"):
            command.add_argument("--replace-pending", action="store_true")
        if name == "generate":
            command.add_argument("--confirm-live-request", action="store_true", required=True)
            command.add_argument("--max-batches", type=int, default=8)
    show = commands.add_parser("show")
    show.add_argument("key")
    review = commands.add_parser("review")
    review.add_argument("key")
    review.add_argument("--reviewer", required=True)
    review.add_argument("--confirm-source-check", action="store_true", required=True)
    args = parser.parse_args(argv)
    service = Path(__file__).resolve().parents[1]
    load_dotenv(service / ".env", override=False)
    directory = args.directory or os.getenv("C4_PREPARED_WORDING_DIR") or service / ".local" / "prepared-wording"
    store = PreparedWordingStore(directory)
    try:
        if args.command == "list":
            keys = store.files.keys()
            if not keys:
                print("No prepared wording bundles.")
            for key in keys:
                try:
                    artifact = store.read(key)
                    if artifact is not None:
                        state = "reviewed" if artifact.review else "pending_review"
                        print(f"{key}  {artifact.origin}  {state}  "
                              f"slots={len(artifact.draft.items)}/{len(artifact.source.targets)}")
                except (ArtifactStoreError, OutputRejected):
                    print(f"{key}  invalid_or_incompatible")
            return 0
        if args.command in ("show", "review"):
            artifact = store.read(args.key)
            if artifact is None:
                raise ArtifactStoreError("wording_not_found")
            if args.command == "review":
                artifact = store.review(args.key, reviewer_reference=args.reviewer)
                print(f"Reviewed {args.key}; origin={artifact.origin}; digest={artifact.review.artifact_digest}")
            else:
                print(artifact.model_dump_json(indent=2))
            return 0
        graph = load_source(args)
        packet = prepare_wording_packet(graph, writing_style=args.style)
        key = wording_key(packet)
        if args.command == "plan":
            batches = preparation_batches(packet)
            print(f"{key}  slots={len(packet.targets)}  batches={len(batches)}  "
                  f"maximum_provider_calls={2 * len(batches)}  live_calls_made=0")
        elif args.command == "template":
            if not args.author.strip():
                raise ValueError("author reference must not be blank")
            # Exclusive creation protects existing editorial work.
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(_canonical(human_template(packet, author_reference=args.author)))
            print(f"Created empty wording template for {len(packet.targets)} slots; key={key}")
        elif args.command in ("validate-human", "import-human"):
            # Editorial filenames need not be SHA keys. Bound the input read.
            with args.input.open("rb") as stream:
                data = stream.read(MAX_ARTIFACT_BYTES + 1)
            if len(data) > MAX_ARTIFACT_BYTES:
                raise ArtifactStoreError("artifact_too_large")
            text = data.decode("utf-8")
            submission = parse_artifact_json(HumanWordingSubmission, text)
            if submission.source != packet:
                raise OutputRejected("wording_submission_does_not_match_current_source")
            artifact = make_human_artifact(
                packet, submission.draft, author_reference=submission.author_reference,
                allow_partial=args.allow_partial,
            )
            if args.command == "import-human":
                store.save(artifact, replace_pending=args.replace_pending)
            print(f"{args.command}: {key}; origin=human_prepared; "
                  f"slots={len(artifact.draft.items)}/{len(packet.targets)}; pending_review")
        elif args.command == "generate":
            if args.max_batches < 1:
                raise ValueError("max-batches must be positive")
            existing = store.read(key)
            if existing is not None and (existing.review is not None or not args.replace_pending):
                print(f"Existing {key}; no provider calls made. Inspect/review or explicitly replace pending content.")
                return 0
            if (os.getenv("C4_DEV_LLM_ENABLED", "false").lower() != "true"
                or os.getenv("C4_LLM_ENABLED", "false").lower() != "true"):
                raise ProviderFailure("provider_disabled")
            provider = OpenAIExplanationProvider.from_environment()
            try:
                artifact = generate_wording(packet, provider, max_batches=args.max_batches)
                store.save(artifact, replace_pending=args.replace_pending)
            finally:
                provider.close()
            print(f"Prepared {key}; origin=provider_generated; pending_review")
        else:
            print(resolve_wording(graph, store, writing_style=args.style).model_dump_json(indent=2))
        return 0
    except (ArtifactStoreError, OutputRejected, ProviderFailure) as exc:
        print(f"Wording operation rejected: {exc}")
        return 1
    except (OSError, ValueError):
        # Do not echo arbitrary input, filesystem errors or source payloads.
        print("Wording operation rejected: invalid_input_or_file_operation")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
