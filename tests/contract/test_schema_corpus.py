"""Validate schema corpus acceptance/rejection against config/schemas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "config" / "schemas"
CORPUS = Path(__file__).parent / "schema-corpus"

SCHEMA_MAP = {
    "runtime-config": "runtime-config-v1.schema.json",
    "forge-config": "forge-config-v1.schema.json",
    "dataset-manifest": "dataset-manifest-v1.schema.json",
    "profile-bundle": "profile-bundle-v1.schema.json",
    "host-fingerprint": "host-fingerprint-v1.schema.json",
    "candidate-manifest": "candidate-manifest-v1.schema.json",
    "benchmark-sample": "benchmark-sample-v1.schema.json",
    "benchmark-summary": "benchmark-summary-v1.schema.json",
    "quality-attestation": "quality-attestation-v1.schema.json",
    "telemetry-event": "telemetry-event-v1.schema.json",
    "preprocess-contract": "preprocess-contract-v1.schema.json",
}


def _offline_registry() -> Registry:
    """Resolve local schema $ref without network access."""
    registry: Registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(raw, default_specification=DRAFT202012)
        schema_id = raw.get("$id", path.as_uri())
        registry = registry.with_resource(schema_id, resource)
        registry = registry.with_resource(path.name, resource)
        # Also register by basename relative URI used in $ref.
        registry = registry.with_resource(f"./{path.name}", resource)
    return registry


def _validator(schema_name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=_offline_registry())


def _cases(kind: str, expect_valid: bool):
    base = CORPUS / kind / ("valid" if expect_valid else "invalid")
    if not base.exists():
        return []
    return sorted(base.glob("*.json"))


@pytest.mark.parametrize(
    "kind",
    [k for k in SCHEMA_MAP if (CORPUS / k).exists()],
)
def test_schema_corpus(kind: str) -> None:
    validator = _validator(SCHEMA_MAP[kind])
    valid_files = _cases(kind, True)
    invalid_files = _cases(kind, False)
    assert valid_files or invalid_files, f"no corpus for {kind}"
    for path in valid_files:
        data = json.loads(path.read_text())
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
        assert not errors, f"{path} should be valid: {errors[0].message if errors else ''}"
    for path in invalid_files:
        data = json.loads(path.read_text())
        errors = list(validator.iter_errors(data))
        assert errors, f"{path} should be invalid"


def test_local_refs_resolve_offline() -> None:
    """preprocess-contract $ref must resolve from the repository schema directory."""
    validator = _validator("dataset-manifest-v1.schema.json")
    # Empty object fails validation but must not raise Unresolvable/network errors.
    errors = list(validator.iter_errors({}))
    assert errors
    joined = " ".join(e.message for e in errors)
    assert "Unresolvable" not in joined
    assert "urlopen" not in joined
