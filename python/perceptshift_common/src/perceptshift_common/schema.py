"""JSON Schema loading and validation against config/schemas contracts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from perceptshift_common.errors import ErrorCode, PerceptShiftError

SCHEMA_FILENAMES: dict[str, str] = {
    "runtime_config": "runtime-config-v1.schema.json",
    "forge_config": "forge-config-v1.schema.json",
    "dataset_manifest": "dataset-manifest-v1.schema.json",
    "candidate_manifest": "candidate-manifest-v1.schema.json",
    "profile_bundle": "profile-bundle-v1.schema.json",
    "benchmark_sample": "benchmark-sample-v1.schema.json",
    "benchmark_summary": "benchmark-summary-v1.schema.json",
    "host_fingerprint": "host-fingerprint-v1.schema.json",
    "quality_attestation": "quality-attestation-v1.schema.json",
    "telemetry_event": "telemetry-event-v1.schema.json",
    "preprocess_contract": "preprocess-contract-v1.schema.json",
}


def repository_root() -> Path:
    """Locate repository root containing config/schemas."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config" / "schemas"
        if candidate.is_dir():
            return parent
    env = Path.cwd()
    if (env / "config" / "schemas").is_dir():
        return env
    raise PerceptShiftError(
        code=ErrorCode.INTERNAL_INVARIANT_FAILED,
        message="Unable to locate config/schemas directory",
        remediation="Run from the PerceptShift repository or install package data correctly",
    )


def schemas_dir() -> Path:
    return repository_root() / "config" / "schemas"


@lru_cache(maxsize=1)
def _registry() -> Registry:
    registry: Registry = Registry()
    for path in sorted(schemas_dir().glob("*.schema.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(raw, default_specification=DRAFT202012)
        schema_id = raw.get("$id", path.as_uri())
        registry = registry.with_resource(schema_id, resource)
        registry = registry.with_resource(path.name, resource)
        registry = registry.with_resource(f"./{path.name}", resource)
        # Support absolute HTTPS $id lookups without network.
        if isinstance(schema_id, str) and schema_id.startswith("https://"):
            registry = registry.with_resource(schema_id.rsplit("/", 1)[-1], resource)
    return registry


@lru_cache(maxsize=32)
def load_schema(name: str) -> dict[str, Any]:
    if name not in SCHEMA_FILENAMES:
        raise PerceptShiftError(
            code=ErrorCode.SCHEMA_UNSUPPORTED,
            message=f"Unknown schema name: {name}",
            details={"known": sorted(SCHEMA_FILENAMES)},
        )
    path = schemas_dir() / SCHEMA_FILENAMES[name]
    if not path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.SCHEMA_UNSUPPORTED,
            message=f"Schema file missing: {path}",
        )
    return json.loads(path.read_text(encoding="utf-8"))


def validate_document(document: dict[str, Any], schema_name: str) -> dict[str, Any]:
    schema = load_schema(schema_name)
    validator = Draft202012Validator(schema, registry=_registry())
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        path = ".".join(str(p) for p in first.absolute_path) or "<root>"
        raise PerceptShiftError(
            code=ErrorCode.CONFIG_INVALID,
            message=f"Schema validation failed at {path}: {first.message}",
            remediation="Fix the document to match config/schemas contracts",
            details={
                "schema": schema_name,
                "error_count": len(errors),
                "path": path,
            },
            cause=first if isinstance(first, JsonSchemaValidationError) else None,
        )
    return document


def load_json_document(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PerceptShiftError(
            code=ErrorCode.CONFIG_INVALID,
            message=f"Failed to load JSON document: {path}",
            cause=exc,
        ) from exc
    if not isinstance(data, dict):
        raise PerceptShiftError(
            code=ErrorCode.CONFIG_INVALID,
            message=f"JSON document must be an object: {path}",
        )
    return data


def load_yaml_document(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PerceptShiftError(
            code=ErrorCode.CONFIG_INVALID,
            message=f"Failed to load YAML document: {path}",
            cause=exc,
        ) from exc
    if not isinstance(data, dict):
        raise PerceptShiftError(
            code=ErrorCode.CONFIG_INVALID,
            message=f"YAML document must be an object: {path}",
        )
    return data


def load_config_document(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return load_yaml_document(path)
    if suffix == ".json":
        return load_json_document(path)
    raise PerceptShiftError(
        code=ErrorCode.CONFIG_INVALID,
        message=f"Unsupported config extension: {suffix}",
        remediation="Use .yaml, .yml, or .json",
    )
