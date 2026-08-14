"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from perceptshift_api.app import create_app
from perceptshift_api.config import Settings, reset_settings_cache
from perceptshift_api.database import reset_database_state


@pytest.fixture
def tmp_dirs(tmp_path: Path) -> dict[str, Path]:
    data = tmp_path / "data"
    state = tmp_path / "state"
    runs = data / "runs"
    bundles = data / "bundles"
    for path in (data, state, runs, bundles):
        path.mkdir(parents=True, exist_ok=True)
    return {"data": data, "state": state, "runs": runs, "bundles": bundles}


@pytest.fixture
def settings(tmp_dirs: dict[str, Path]) -> Settings:
    reset_settings_cache()
    reset_database_state()
    return Settings(
        host="127.0.0.1",
        port=8741,
        mutation_token=None,
        cors_origins=[],
        data_dir=tmp_dirs["data"],
        state_dir=tmp_dirs["state"],
        artifact_roots=[tmp_dirs["runs"], tmp_dirs["bundles"]],
        enable_ros=False,
        database_url=f"sqlite:///{tmp_dirs['state'] / 'test.sqlite'}",
        max_request_bytes=4096,
        websocket_queue_size=4,
        websocket_max_clients=8,
    )


@pytest.fixture
def settings_with_token(settings: Settings) -> Settings:
    return settings.model_copy(update={"mutation_token": "test-mutation-token-value"})


@pytest.fixture
async def client(settings: Settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8741") as ac:
            yield ac, app
    reset_database_state()
    reset_settings_cache()


@pytest.fixture
async def auth_client(settings_with_token: Settings):
    app = create_app(settings_with_token)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8741") as ac:
            yield ac, app, settings_with_token.mutation_token
    reset_database_state()
    reset_settings_cache()
