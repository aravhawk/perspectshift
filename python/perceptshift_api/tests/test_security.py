"""Path allowlist, SQLi resistance, oversized requests, OpenAPI."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from perceptshift_api.database import get_session_factory
from perceptshift_api.models import ArtifactRecord, RunRecord, utcnow


async def test_path_traversal_rejected(auth_client, tmp_dirs) -> None:
    ac, _app, token = auth_client
    headers = {"Authorization": f"Bearer {token}"}
    response = await ac.post(
        "/api/v1/bundles/verify",
        json={"path": str(tmp_dirs["bundles"] / ".." / ".." / "etc" / "passwd")},
        headers=headers,
    )
    assert response.status_code in {400, 403}
    assert response.json()["error"]["code"] in {"PATH_TRAVERSAL", "PATH_NOT_ALLOWED"}


async def test_absolute_path_outside_roots(auth_client) -> None:
    ac, _app, token = auth_client
    headers = {"Authorization": f"Bearer {token}"}
    response = await ac.post(
        "/api/v1/bundles/verify",
        json={"path": "/tmp/not-allowed/bundle.json"},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PATH_NOT_ALLOWED"


async def test_symlink_escape_rejected(auth_client, tmp_dirs) -> None:
    ac, _app, token = auth_client
    outside = tmp_dirs["data"].parent / "secret.json"
    outside.write_text('{"bundle_id":"x"}', encoding="utf-8")
    link = tmp_dirs["bundles"] / "escape.json"
    link.symlink_to(outside)

    headers = {"Authorization": f"Bearer {token}"}
    response = await ac.post(
        "/api/v1/bundles/verify",
        json={"path": str(link)},
        headers=headers,
    )
    # Resolved target is outside roots.
    assert response.status_code in {403, 400}
    assert response.json()["error"]["code"] in {
        "PATH_NOT_ALLOWED",
        "PATH_TRAVERSAL",
        "PATH_INVALID",
    }


async def test_artifact_allowlist_and_traversal_id(client, tmp_dirs) -> None:
    ac, _app = client
    factory = get_session_factory()
    session: Session = factory()
    run_dir = tmp_dirs["runs"] / "run-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = run_dir / "summary.json"
    artifact_path.write_text('{"ok":true}', encoding="utf-8")
    session.add(
        RunRecord(
            run_id="run-1",
            host="test-host",
            valid=True,
            candidate_count=0,
            workspace_path=str(run_dir),
            import_status="indexed",
            pinned=False,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    session.add(
        ArtifactRecord(
            artifact_id="summary",
            run_id="run-1",
            kind="json",
            path=str(artifact_path),
            content_type="application/json",
            created_at=utcnow(),
        )
    )
    session.commit()
    session.close()

    ok = await ac.get("/api/v1/runs/run-1/artifacts/summary")
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}

    bad = await ac.get("/api/v1/runs/run-1/artifacts/evil..path")
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "PATH_TRAVERSAL"


async def test_sql_injection_resistant_lookup(client) -> None:
    ac, _app = client
    response = await ac.get("/api/v1/runs/run-1'%20OR%201=1--")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"


async def test_oversized_request_rejected(client) -> None:
    ac, _app = client
    payload = {"deadline_ms": 1.0}
    # Content-Length larger than configured max (4096)
    response = await ac.patch(
        "/api/v1/runtime/policy",
        content=json.dumps(payload),
        headers={"Content-Length": "99999", "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


async def test_malformed_json(auth_client) -> None:
    ac, _app, token = auth_client
    response = await ac.patch(
        "/api/v1/runtime/policy",
        content="{not-json",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_openapi_schema_valid(client) -> None:
    ac, _app = client
    response = await ac.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "PerceptShift Local API"
    paths = schema["paths"]
    for required in (
        "/api/v1/healthz",
        "/api/v1/runtime/status",
        "/api/v1/profiles",
        "/api/v1/telemetry/recent",
        "/api/v1/bundles/current",
        "/api/v1/runs",
    ):
        assert required in paths


async def test_bundle_verify_success(auth_client, tmp_dirs) -> None:
    ac, _app, token = auth_client
    manifest = tmp_dirs["bundles"] / "bundle.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "document_type": "perceptshift.profile_bundle",
                "bundle_id": "b1",
                "files": {"model.onnx": {"sha256": "abc"}},
            }
        ),
        encoding="utf-8",
    )
    response = await ac.post(
        "/api/v1/bundles/verify",
        json={"path": str(manifest)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["integrity_status"] == "hash_computed"
    assert body["details"]["bundle_id"] == "b1"


def test_loopback_default_in_settings() -> None:
    from perceptshift_api.config import Settings

    s = Settings()
    assert s.host == "127.0.0.1"
