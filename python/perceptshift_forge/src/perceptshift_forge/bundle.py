"""Profile bundle verify / import / sign helpers (Ed25519)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_file, write_atomic_json, write_atomic_text
from perceptshift_common.producer import envelope_fields
from perceptshift_common.schema import load_json_document, validate_document

_SIG_PAYLOAD_SCHEMA_VERSION = "1"


def verify_bundle(
    bundle_root: Path,
    *,
    public_key: bytes | None = None,
    require_signature: bool = False,
) -> dict[str, Any]:
    if not bundle_root.is_dir():
        raise PerceptShiftError(
            code=ErrorCode.BUNDLE_INVALID,
            message=f"Bundle root is not a directory: {bundle_root}",
        )
    manifest_path = bundle_root / "manifest.json"
    digest_path = bundle_root / "manifest.sha256"
    if not manifest_path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.BUNDLE_INVALID,
            message="manifest.json missing",
        )
    if not digest_path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.FILE_INTEGRITY_FAILED,
            message="manifest.sha256 missing",
        )
    manifest = load_json_document(manifest_path)
    validate_document(manifest, "profile_bundle")
    expected = digest_path.read_text(encoding="utf-8").strip().split()[0]
    actual = sha256_file(manifest_path)
    if expected != actual:
        raise PerceptShiftError(
            code=ErrorCode.FILE_INTEGRITY_FAILED,
            message="manifest.sha256 does not match manifest.json",
            details={"expected": expected, "actual": actual},
        )

    inventory = manifest.get("files") or []
    checked: list[dict[str, Any]] = []
    inventoried: set[str] = set()
    for entry in inventory:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("path") or entry.get("relative_path")
        digest = entry.get("sha256")
        if not isinstance(rel, str) or not isinstance(digest, str):
            continue
        if Path(rel).is_absolute() or rel.startswith("/") or ".." in Path(rel).parts:
            raise PerceptShiftError(
                code=ErrorCode.PATH_UNSAFE,
                message=f"Inventory path must be relative without '..': {rel}",
            )
        target = (bundle_root / rel).resolve()
        try:
            target.relative_to(bundle_root.resolve())
        except ValueError as exc:
            raise PerceptShiftError(
                code=ErrorCode.PATH_UNSAFE,
                message=f"Inventory path escapes bundle root: {rel}",
            ) from exc
        if not target.is_file():
            raise PerceptShiftError(
                code=ErrorCode.BUNDLE_INVALID,
                message=f"Missing inventoried file: {rel}",
            )
        got = sha256_file(target)
        if got != digest:
            raise PerceptShiftError(
                code=ErrorCode.FILE_INTEGRITY_FAILED,
                message=f"Hash mismatch for {rel}",
                details={"expected": digest, "actual": got},
            )
        inventoried.add(Path(rel).as_posix())
        checked.append({"path": rel, "sha256": got})

    # Reject undeclared model artifacts.
    for path in bundle_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(bundle_root).as_posix()
        if rel in {"manifest.json", "manifest.sha256", "manifest.sig", "manifest.mac"}:
            continue
        if path.suffix == ".onnx" and rel not in inventoried:
            raise PerceptShiftError(
                code=ErrorCode.FILE_INTEGRITY_FAILED,
                message=f"Undeclared model artifact in bundle: {rel}",
            )

    sig_path = bundle_root / "manifest.sig"
    signature_present = sig_path.is_file()
    signature_ok: bool | None = None
    signature_meta: dict[str, Any] | None = None
    if signature_present:
        signature_meta = verify_bundle_signature(bundle_root, public_key_bytes=public_key)
        signature_ok = True
    elif require_signature:
        raise PerceptShiftError(
            code=ErrorCode.SIGNATURE_REQUIRED,
            message="Bundle signature required but manifest.sig is missing",
        )

    report = envelope_fields(document_type="perceptshift.bundle_verify")
    report.update(
        {
            "bundle_root": str(bundle_root),
            "ok": True,
            "manifest_sha256": actual,
            "files_checked": checked,
            "signature_present": signature_present,
            "signature_ok": signature_ok,
            "signature_verified": bool(signature_ok),
            "signature_algorithm": "ed25519" if signature_ok else None,
            "signature": signature_meta,
        }
    )
    return report


def import_bundle(bundle_root: Path, destination: Path) -> dict[str, Any]:
    verify_bundle(bundle_root)
    destination.mkdir(parents=True, exist_ok=True)
    import shutil

    target = destination / bundle_root.name
    if target.exists():
        raise PerceptShiftError(
            code=ErrorCode.BUNDLE_INVALID,
            message=f"Destination already exists: {target}",
        )
    shutil.copytree(bundle_root, target)
    report = envelope_fields(document_type="perceptshift.bundle_import")
    report.update({"source": str(bundle_root), "destination": str(target), "ok": True})
    return report


def sign_bundle(
    bundle_root: Path,
    *,
    key_path: Path,
    key_id: str | None = None,
    include_public_key: bool = True,
) -> dict[str, Any]:
    """Detach-sign ``manifest.sha256`` bytes with Ed25519.

    Writes ``manifest.sig`` as JSON metadata so the algorithm cannot be confused
    with a keyed BLAKE2b MAC.
    """
    verify_bundle(bundle_root)
    private_key = _load_ed25519_private_key(key_path)
    payload = (bundle_root / "manifest.sha256").read_bytes()
    signature = private_key.sign(payload)
    public_key_hex = private_key.public_key().public_bytes_raw().hex()
    resolved_key_id = key_id or hashlib.sha256(bytes.fromhex(public_key_hex)).hexdigest()[:16]
    sig_doc: dict[str, Any] = {
        "algorithm": "ed25519",
        "key_id": resolved_key_id,
        "payload_schema_version": _SIG_PAYLOAD_SCHEMA_VERSION,
        "encoding": "hex",
        "signature": signature.hex(),
    }
    if include_public_key:
        sig_doc["public_key"] = public_key_hex
    sig_path = bundle_root / "manifest.sig"
    write_atomic_json(sig_path, sig_doc)
    try:
        sig_path.chmod(0o600)
    except OSError:
        pass
    report = envelope_fields(document_type="perceptshift.bundle_sign")
    report.update(
        {
            "bundle_root": str(bundle_root),
            "signature_path": str(sig_path),
            "algorithm": "ed25519",
            "key_id": resolved_key_id,
            "ok": True,
        }
    )
    return report


def verify_bundle_signature(
    bundle_root: Path,
    *,
    public_key_path: Path | None = None,
    public_key_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Verify Ed25519 signature over the exact bytes of ``manifest.sha256``."""
    sig_path = bundle_root / "manifest.sig"
    digest_path = bundle_root / "manifest.sha256"
    if not sig_path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.SIGNATURE_REQUIRED,
            message="manifest.sig missing",
        )
    if not digest_path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.FILE_INTEGRITY_FAILED,
            message="manifest.sha256 missing",
        )
    raw = sig_path.read_text(encoding="utf-8").strip()
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PerceptShiftError(
            code=ErrorCode.SIGNATURE_INVALID,
            message=(
                "manifest.sig must be Ed25519 JSON metadata; "
                "legacy blake2b-keyed-32 hex signatures are not accepted"
            ),
            cause=exc,
        ) from exc
    if not isinstance(meta, dict):
        raise PerceptShiftError(
            code=ErrorCode.SIGNATURE_INVALID,
            message="manifest.sig JSON must be an object",
        )
    algorithm = str(meta.get("algorithm") or "").lower()
    if algorithm != "ed25519":
        raise PerceptShiftError(
            code=ErrorCode.SIGNATURE_INVALID,
            message=f"Unsupported signature algorithm: {algorithm}",
            remediation="Re-sign the bundle with Ed25519",
        )
    if meta.get("encoding") not in {None, "hex"}:
        raise PerceptShiftError(
            code=ErrorCode.SIGNATURE_INVALID,
            message=f"Unsupported signature encoding: {meta.get('encoding')}",
        )
    sig_hex = meta.get("signature")
    if not isinstance(sig_hex, str) or len(sig_hex) != 128:
        raise PerceptShiftError(
            code=ErrorCode.SIGNATURE_INVALID,
            message="Ed25519 signature must be 128 hex characters (64 bytes)",
        )
    try:
        signature = bytes.fromhex(sig_hex)
    except ValueError as exc:
        raise PerceptShiftError(
            code=ErrorCode.SIGNATURE_INVALID,
            message="Signature is not valid hex",
            cause=exc,
        ) from exc

    if public_key_bytes is not None:
        if len(public_key_bytes) != 32:
            raise PerceptShiftError(
                code=ErrorCode.SIGNATURE_INVALID,
                message="Ed25519 public key must be 32 bytes",
            )
        public_key = _public_key_from_bytes(public_key_bytes)
        public_key_hex = public_key_bytes.hex()
    elif public_key_path is not None:
        public_key = _load_ed25519_public_key(public_key_path)
        public_key_hex = public_key.public_bytes_raw().hex()
    else:
        pub_hex = meta.get("public_key")
        if not isinstance(pub_hex, str) or len(pub_hex) != 64:
            raise PerceptShiftError(
                code=ErrorCode.SIGNATURE_INVALID,
                message="public_key missing in manifest.sig; supply public key",
            )
        public_key = _public_key_from_hex(pub_hex)
        public_key_hex = pub_hex

    payload = digest_path.read_bytes()
    try:
        public_key.verify(signature, payload)
    except Exception as exc:  # cryptography raises InvalidSignature
        raise PerceptShiftError(
            code=ErrorCode.SIGNATURE_INVALID,
            message="Ed25519 signature verification failed",
            remediation="Ensure the correct public key and untampered manifest.sha256",
            cause=exc,
        ) from exc

    return {
        "algorithm": "ed25519",
        "key_id": meta.get("key_id"),
        "payload_schema_version": meta.get("payload_schema_version"),
        "public_key": public_key_hex,
        "ok": True,
    }


def integrity_mac_blake2b(
    bundle_root: Path,
    *,
    key_path: Path,
) -> dict[str, Any]:
    """Optional local integrity MAC (not an Ed25519 signature).

    Writes ``manifest.mac`` — never ``manifest.sig``.
    """
    verify_bundle(bundle_root)
    if not key_path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.SIGNATURE_REQUIRED,
            message=f"MAC key not found: {key_path}",
        )
    key = key_path.read_bytes()
    payload = (bundle_root / "manifest.sha256").read_bytes()
    digest = hashlib.blake2b(payload, key=key[:64], digest_size=32).hexdigest()
    mac_path = bundle_root / "manifest.mac"
    write_atomic_text(
        mac_path,
        json.dumps(
            {
                "algorithm": "blake2b-keyed-32",
                "encoding": "hex",
                "mac": digest,
            },
            separators=(",", ":"),
        )
        + "\n",
    )
    report = envelope_fields(document_type="perceptshift.bundle_mac")
    report.update(
        {
            "bundle_root": str(bundle_root),
            "mac_path": str(mac_path),
            "algorithm": "blake2b-keyed-32",
            "ok": True,
        }
    )
    return report


def _require_cryptography() -> Any:
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as exc:
        raise PerceptShiftError(
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            message="cryptography package is required for Ed25519 signing",
            remediation="Install cryptography via perceptshift-forge dependencies",
            cause=exc,
        ) from exc
    return ed25519


def _load_ed25519_private_key(key_path: Path) -> Any:
    ed25519 = _require_cryptography()
    if not key_path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.SIGNATURE_REQUIRED,
            message=f"Signing key not found: {key_path}",
        )
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    raw = key_path.read_bytes()
    if b"BEGIN" in raw:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        loaded = load_pem_private_key(raw, password=None)
        if not isinstance(loaded, ed25519.Ed25519PrivateKey):
            raise PerceptShiftError(
                code=ErrorCode.SIGNATURE_INVALID,
                message="PEM key is not an Ed25519 private key",
            )
        return loaded
    text = raw.decode("utf-8", errors="ignore").strip()
    if len(text) == 64 and all(c in "0123456789abcdefABCDEF" for c in text):
        return ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(text))
    if len(raw) == 32:
        return ed25519.Ed25519PrivateKey.from_private_bytes(raw)
    raise PerceptShiftError(
        code=ErrorCode.SIGNATURE_INVALID,
        message="Ed25519 private key must be 32 raw bytes, 64 hex chars, or PEM",
    )


def _load_ed25519_public_key(key_path: Path) -> Any:
    ed25519 = _require_cryptography()
    raw = key_path.read_bytes()
    if b"BEGIN" in raw:
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        loaded = load_pem_public_key(raw)
        if not isinstance(loaded, ed25519.Ed25519PublicKey):
            raise PerceptShiftError(
                code=ErrorCode.SIGNATURE_INVALID,
                message="PEM key is not an Ed25519 public key",
            )
        return loaded
    text = raw.decode("utf-8", errors="ignore").strip()
    if len(text) == 64 and all(c in "0123456789abcdefABCDEF" for c in text):
        return _public_key_from_hex(text)
    if len(raw) == 32:
        return ed25519.Ed25519PublicKey.from_public_bytes(raw)
    raise PerceptShiftError(
        code=ErrorCode.SIGNATURE_INVALID,
        message="Ed25519 public key must be 32 raw bytes, 64 hex chars, or PEM",
    )


def _public_key_from_hex(pub_hex: str) -> Any:
    return _public_key_from_bytes(bytes.fromhex(pub_hex))


def _public_key_from_bytes(raw: bytes) -> Any:
    ed25519 = _require_cryptography()
    try:
        return ed25519.Ed25519PublicKey.from_public_bytes(raw)
    except Exception as exc:
        raise PerceptShiftError(
            code=ErrorCode.SIGNATURE_INVALID,
            message="Invalid Ed25519 public key",
            cause=exc,
        ) from exc
