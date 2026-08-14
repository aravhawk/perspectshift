"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from perceptshift_api import __version__
from perceptshift_api.auth import MutationRateLimiter
from perceptshift_api.config import Settings, get_settings, reset_settings_cache
from perceptshift_api.database import init_database, reset_database_state
from perceptshift_api.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from perceptshift_api.middleware import RequestSizeLimitMiddleware, SecurityHeadersMiddleware
from perceptshift_api.ros_bridge import RosBridge
from perceptshift_api.routers import bundles, profiles, runs, runtime, system, telemetry
from perceptshift_api.telemetry import TelemetryHub

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_database(app_settings)
        hub = TelemetryHub(
            cache_size=app_settings.telemetry_cache_size,
            queue_size=app_settings.websocket_queue_size,
            max_clients=app_settings.websocket_max_clients,
        )
        bridge = RosBridge(
            hub,
            enable_ros=app_settings.enable_ros,
            service_timeout_s=app_settings.ros_service_timeout_s,
            stale_after_s=app_settings.ros_stale_after_s,
            runtime_node=app_settings.ros_runtime_node,
            pin_duration_seconds=app_settings.ros_pin_duration_seconds,
        )
        loop = asyncio.get_running_loop()

        def publish_from_bridge(
            event_type: str,
            payload: dict[str, Any],
            *,
            trace_id: str | None = None,
        ) -> None:
            future = asyncio.run_coroutine_threadsafe(
                hub.publish(event_type, payload, trace_id=trace_id),
                loop,
            )
            try:
                future.result(timeout=1.0)
            except Exception:
                logger.debug("bridge telemetry publish failed", exc_info=True)

        bridge.set_loop_publish(publish_from_bridge)
        bridge.start()
        app.state.settings = app_settings
        app.state.telemetry_hub = hub
        app.state.ros_bridge = bridge
        app.state.mutation_rate_limiter = MutationRateLimiter(
            app_settings.rate_limit_mutations_per_minute
        )
        await hub.emit_connection_status(
            "api_started",
            {"mode": "artifact_store" if not bridge.state.connected else "ros"},
        )
        try:
            yield
        finally:
            bridge.set_loop_publish(None)
            bridge.stop()
            reset_database_state()

    app = FastAPI(
        title="PerceptShift Local API",
        version=__version__,
        description="Local operational API for PerceptShift. Not a source of runtime truth.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Starlette's ExceptionHandler typing is invariant on the exception parameter;
    # cast keeps runtime registration while satisfying the checker.
    app.add_exception_handler(ApiError, cast(Any, api_error_handler))
    app.add_exception_handler(StarletteHTTPException, cast(Any, http_exception_handler))
    app.add_exception_handler(RequestValidationError, cast(Any, validation_exception_handler))
    app.add_exception_handler(Exception, cast(Any, unhandled_exception_handler))

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=app_settings.max_request_bytes)

    origins = app_settings.effective_cors_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
        )

    app.include_router(system.router, prefix="/api/v1")
    app.include_router(runtime.router, prefix="/api/v1")
    app.include_router(profiles.router, prefix="/api/v1")
    app.include_router(telemetry.router, prefix="/api/v1")
    app.include_router(bundles.router, prefix="/api/v1")
    app.include_router(runs.router, prefix="/api/v1")

    # Root probes for local process managers.
    app.include_router(system.router, prefix="", include_in_schema=False)

    if settings is not None:
        from perceptshift_api.dependencies import settings_dep

        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[settings_dep] = lambda: settings
        reset_settings_cache()

    return app


app = create_app()
