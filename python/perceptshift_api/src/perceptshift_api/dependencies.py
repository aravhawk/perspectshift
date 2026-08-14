"""FastAPI dependency providers."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from perceptshift_api.auth import MutationRateLimiter, require_mutation_auth
from perceptshift_api.config import Settings, get_settings
from perceptshift_api.database import get_session_factory
from perceptshift_api.ros_bridge import RosBridge
from perceptshift_api.telemetry import TelemetryHub


def settings_dep() -> Settings:
    return get_settings()


def db_session() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def hub_dep(request: Request) -> TelemetryHub:
    return request.app.state.telemetry_hub


def ros_dep(request: Request) -> RosBridge:
    return request.app.state.ros_bridge


def rate_limiter_dep(request: Request) -> MutationRateLimiter:
    return request.app.state.mutation_rate_limiter


def require_mutations(
    request: Request,
    settings: Annotated[Settings, Depends(settings_dep)],
    limiter: Annotated[MutationRateLimiter, Depends(rate_limiter_dep)],
) -> str:
    actor = require_mutation_auth(request, settings)
    client = request.client.host if request.client else "unknown"
    limiter.check(client)
    return actor


SettingsDep = Annotated[Settings, Depends(settings_dep)]
DbDep = Annotated[Session, Depends(db_session)]
HubDep = Annotated[TelemetryHub, Depends(hub_dep)]
RosDep = Annotated[RosBridge, Depends(ros_dep)]
MutationActorDep = Annotated[str, Depends(require_mutations)]
