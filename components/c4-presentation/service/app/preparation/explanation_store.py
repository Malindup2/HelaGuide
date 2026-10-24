"""Trusted local wording assets, separate from sessions and learned state.

Review metadata is an audit declaration, not a cryptographic signature.
Only trusted operators should have write access to this directory.
"""

import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from pydantic import JsonValue

from app.models.explanations import CachedExplanation
from app.models.procedure_graph import GraphRecord


MAX_ARTIFACT_BYTES = 2_000_000
_KEY = re.compile(r"[0-9a-f]{64}\Z")


class ArtifactStoreError(ValueError):
    """Safe diagnostics; never include local contents or credentials."""


class StoredExplanation(GraphRecord):
    schema_version: Literal["c4-wording-store-1.0"] = "c4-wording-store-1.0"
    source_packet: dict[str, JsonValue]
    artifact: CachedExplanation


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactStoreError("artifact_duplicate_json_key")
        result[key] = value
    return result


def parse_artifact_json(model, text: str):
    try:
        if len(text.encode("utf-8")) > MAX_ARTIFACT_BYTES:
            raise ArtifactStoreError("artifact_too_large")
        def reject_constant(value):
            raise ArtifactStoreError("artifact_non_finite_number")
        json.loads(text, object_pairs_hook=_unique, parse_constant=reject_constant)
        return model.model_validate_json(text, strict=True)
    except ArtifactStoreError:
        raise
    except (ValueError, RecursionError):
        raise ArtifactStoreError("artifact_invalid_schema") from None


def parse_stored(text: str) -> StoredExplanation:
    return parse_artifact_json(StoredExplanation, text)


class ExplanationArtifactStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory).resolve()

    def _path(self, key: str) -> Path:
        if not isinstance(key, str) or _KEY.fullmatch(key) is None:
            raise ArtifactStoreError("artifact_invalid_key")
        path = self.directory / (key + ".json")
        if path.is_symlink():
            raise ArtifactStoreError("artifact_symlink_rejected")
        return path

    def read_text(self, key: str) -> str | None:
        path = self._path(key)
        try:
            with path.open("rb") as stream:
                data = stream.read(MAX_ARTIFACT_BYTES + 1)
            if len(data) > MAX_ARTIFACT_BYTES:
                raise ArtifactStoreError("artifact_too_large")
            return data.decode("utf-8")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError):
            raise ArtifactStoreError("artifact_read_failed") from None

    def read(self, key: str) -> StoredExplanation | None:
        text = self.read_text(key)
        if text is None:
            return None
        stored = parse_stored(text)
        if stored.artifact.request_key != key:
            raise ArtifactStoreError("artifact_filename_mismatch")
        return stored

    def write(self, stored: StoredExplanation) -> None:
        self.write_text(stored.artifact.request_key, stored.model_dump_json(indent=2))

    def write_text(self, key: str, text: str) -> None:
        path = self._path(key)
        data = text.encode("utf-8")
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ArtifactStoreError("artifact_too_large")
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode="wb", dir=self.directory, prefix=".wording-", suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError:
            raise ArtifactStoreError("artifact_write_failed") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def keys(self) -> tuple[str, ...]:
        try:
            return tuple(sorted(
                path.stem for path in self.directory.glob("*.json")
                if _KEY.fullmatch(path.stem)
            ))
        except OSError:
            raise ArtifactStoreError("artifact_list_failed") from None
