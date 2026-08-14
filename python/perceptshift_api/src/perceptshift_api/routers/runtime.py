"""Runtime status, health, policy, and recovery endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from perceptshift_api.audit import record_audit
from perceptshift_api.dependencies import DbDep, MutationActorDep, RosDep
from perceptshift_api.errors import ApiError
from perceptshift_api.schemas import (
    RecoveryRequest,
    RuntimeHealth,
    RuntimePolicy,
    RuntimePolicyPatch,
    RuntimeStatus,
)

router = APIRouter(prefix="/runtime", tags=["runtime"])


def _ros_mutation(call):
    try:
        return call()
    except ApiError:
        raise
    except TimeoutError as exc:
        raise ApiError(
            "ROS_TIMEOUT",
            str(exc),
            status_code=504,
            retryable=True,
            remediation="Retry; if persistent, inspect runtime node load and DDS discovery",
        ) from exc
    except RuntimeError as exc:
        raise ApiError(
            "ROS_SERVICE_FAILED",
            str(exc),
            status_code=503,
            retryable=True,
            remediation="Ensure the ROS runtime node is active and mutation services are enabled",
        ) from exc


@router.get("/status", response_model=RuntimeStatus)
def runtime_status(ros: RosDep) -> RuntimeStatus:
    return ros.runtime_status()


@router.get("/health", response_model=RuntimeHealth)
def runtime_health(ros: RosDep) -> RuntimeHealth:
    return ros.runtime_health()


@router.get("/policy", response_model=RuntimePolicy)
def runtime_policy(ros: RosDep) -> RuntimePolicy:
    return ros.runtime_policy()


@router.patch("/policy", response_model=RuntimePolicy)
def patch_runtime_policy(
    body: RuntimePolicyPatch,
    request: Request,
    ros: RosDep,
    db: DbDep,
    actor: MutationActorDep,
) -> RuntimePolicy:
    updated = _ros_mutation(lambda: ros.set_policy(body.model_dump(exclude_unset=True)))
    record_audit(
        db,
        actor=actor,
        action="runtime.policy.patch",
        details=body.model_dump(exclude_unset=True),
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return updated


@router.post("/recovery")
def runtime_recovery(
    body: RecoveryRequest,
    request: Request,
    ros: RosDep,
    db: DbDep,
    actor: MutationActorDep,
) -> dict[str, object]:
    result = _ros_mutation(lambda: ros.recovery(body.action))
    record_audit(
        db,
        actor=actor,
        action="runtime.recovery",
        details={"action": body.action},
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return result
