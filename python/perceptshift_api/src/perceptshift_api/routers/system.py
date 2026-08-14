"""System endpoints: health, readiness, version, capabilities."""

from __future__ import annotations

from fastapi import APIRouter

from perceptshift_api import __version__
from perceptshift_api.database import ping_database
from perceptshift_api.dependencies import RosDep, SettingsDep
from perceptshift_api.schemas import Capabilities, Healthz, Readyz, VersionInfo

router = APIRouter(tags=["system"])


@router.get("/healthz", response_model=Healthz)
def healthz() -> Healthz:
    return Healthz()


@router.get("/readyz", response_model=Readyz)
def readyz(settings: SettingsDep, ros: RosDep) -> Readyz:
    reasons: list[str] = []
    db_ok = False
    try:
        db_ok = ping_database()
    except Exception:  # noqa: BLE001
        reasons.append("DATABASE_UNAVAILABLE")

    ros_state = ros.state
    ros_label = "connected" if ros_state.connected else ros_state.reason_code
    # Artifact-store mode is ready for run inspection without ROS.
    ready = db_ok
    if settings.enable_ros and ros_state.mode == "ros" and not ros_state.connected:
        # Still ready for artifact operations; surface ROS absence in reasons.
        reasons.append(ros_state.reason_code)
    return Readyz(ready=ready, database=db_ok, ros=ros_label, reasons=reasons)


@router.get("/version", response_model=VersionInfo)
def version() -> VersionInfo:
    return VersionInfo(api_version=__version__)


@router.get("/capabilities", response_model=Capabilities)
def capabilities(settings: SettingsDep, ros: RosDep) -> Capabilities:
    return Capabilities(
        mutations_enabled=settings.mutations_enabled(),
        ros_bridge=ros.state.reason_code if not ros.state.connected else "connected",
        cors_origins=settings.effective_cors_origins(),
        bind_host=settings.host,
        max_request_bytes=settings.max_request_bytes,
    )
