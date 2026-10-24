# Durable reviewed explanation content

This workflow belongs only to `app.dev_main:app`. It does not change the
team's `app.main:app` stub, shared contracts, 64 configurations, 656 policy
features, session format or feedback attribution.

## Runtime configuration

The independent backend loads `service/.env`, with existing shell variables
taking precedence. Do not put credentials in a committed file. The frontend
never needs an API key. Restart the backend after changing these settings.

```dotenv
C4_DEV_LLM_ENABLED=false
C4_LLM_ENABLED=false
C4_REVIEWED_CONTENT_ONLY=true
# Optional absolute directory; default is service/.local/wording-artifacts
# C4_CONTENT_DIR=C:/Users/Lenovo/Documents/HelaGuide-local-content
```

`C4_DEV_LLM_ENABLED` and `C4_LLM_ENABLED` must BOTH be true for the
environment-created backend to generate. Turning either off prevents calls.
`C4_REVIEWED_CONTENT_ONLY=true` is the server default: pending content is
saved but not shown as an approved explanation. Missing, malformed, stale,
incompatible or unreviewed content produces the existing source-copy fallback
and a diagnostic in the explanation result. An invalid package is not
automatically overwritten or repeatedly regenerated.

The `/health` response includes `content.persistent_artifacts`,
`content.reviewed_only` and `content.generation_enabled`. These describe
configuration, not evidence that real generation or review has succeeded.
Existing saved presentations remain historical snapshots; request fresh
guidance to exercise current artifact retrieval and review enforcement.

## Preparation and actual human review

From `components/c4-presentation/service/`, use the existing Python environment.
This milestone does not ship invented reviewed explanations or automatically
approve content. Tests use an explicitly fake provider and are not live LLM
evidence.

1. For a deliberately bounded live preparation session, configure your local
   key and approved model, turn both live gates on and keep reviewed-only true.
   Use the normal guidance request to generate the needed content. Each cache
   miss can make one generation call and one assessment call. These cost API
   credits. A successful pair creates a pending package. A provider failure
   creates no approved artifact. Real provider/model success must be checked
   separately; this feature does not imply that an account has credits or that
   a model identifier is available.
2. List the packages:

   ```powershell
   .\.venv\Scripts\python.exe -m app.preparation.content_cli list
   ```

3. Inspect one package, replacing `KEY` with its full 64-character key:

   ```powershell
   .\.venv\Scripts\python.exe -m app.preparation.content_cli show KEY
   ```

   Alternatively open the JSON in VS Code. Read every draft against the source
   packet, citations, facts, conditions, prerequisites and source warnings.
   Check negation, alternative applicability and uncertainty. Automated
   assessment is fallible. Do not approve an unsupported draft. Keep pending
   content unapproved if uncertain. Correcting prose changes the exact artifact;
   it must be revalidated and reviewed, not silently retain its old digest.
4. Only after that human check, attest to the exact artifact:

   ```powershell
   .\.venv\Scripts\python.exe -m app.preparation.content_cli review KEY --reviewer local-review-1 --confirm-source-check
   ```

   Use a non-personal reviewer reference. The command records an attestation;
   it cannot perform or authenticate a human review. Provider name, model,
   response IDs, token usage, generation timestamp and assessment stay intact.
   A fake/test provider is never relabeled as OpenAI by review.
5. Turn both live gates off, restart the backend and request NEW guidance.
   Inspect its explanation: `origin=generated`, `cache_hit=true`,
   `assurance=human_reviewed_against_supplied_sources`. Its artifact retains
   the original provider call records; they are not calls made on cache reuse.
   Restart again and repeat. New presentation/exposure IDs must bind to the
   new request, while the content key remains the same for equivalent input.

The `--directory ABSOLUTE_PATH` option goes before `list`, `show` or `review`
when operating on a different store. The runtime and tooling must use the same
directory. Copying this complete folder to another trusted local machine is
possible; no automatic publication/import endpoint exists.

## Compatibility and limits

The key retains the existing exact binding to graph fingerprint, full source
packet, writing style, selected scaffold configuration, provider/model/SDK
identity, prompts, schemas and validation version. Disabling live requests
keeps the configured provider/model identity intact. Keep `C4_LLM_MODEL`
consistent between preparation and demonstration. SDK or content changes
invalidate reuse conservatively; fallback is correct until replacement
content is prepared and reviewed. Old files are not deleted automatically.

M1 preserves this configuration-specific key. An artifact for one scaffold
configuration or writing style does not cover every other configuration.
Standard and personalized packets also differ. M2 adds the reusable wording
contract and broader preparation coverage; do not promise every possible
adaptive selection has prepared content after generating a single request.

Files are read lazily on each request, so reuse does not depend on startup
import order or the 128-entry RAM cache. Deleting approval from disk takes
effect for new requests even when content was previously cached in memory.
Writes use a same-directory temporary file, flush and atomic replacement.
This is a local prototype store, not a multi-writer editorial database: run
one preparation/review writer at a time and disable generation while reviewing.
No runtime database migration is needed.

The store contains procedure source packets and generated wording, not API
keys, user profiles or policy rewards. The supplied-source packet excludes
session/exposure IDs. Review digests detect accidental changes; an actor with
directory write access could forge review metadata. Use a trusted folder.
File integrity and model assessment do not prove official source authenticity.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_reviewed_content.py tests/test_explanations.py tests/test_llm_provider.py
.\.venv\Scripts\python.exe -m pytest -q
```

The tests cover fresh-request reuse after restart, exact source/style/model
binding, pending review, tampering, corrupt JSON, disk failures, revocation,
honest fake-provider provenance and unchanged policy revision on content reuse.
All fixtures are temporary and provider calls are fake. PostgreSQL integration
requires its separate dedicated test database; never target demonstration
data with the integration-test DSN.
