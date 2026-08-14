"""Audit event helpers."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from perceptshift_api.models import AuditEventRecord


def record_audit(
    session: Session,
    *,
    actor: str,
    action: str,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> None:
    session.add(
        AuditEventRecord(
            actor=actor,
            action=action,
            target=target,
            details_json=json.dumps(details or {}, separators=(",", ":")),
            correlation_id=correlation_id,
        )
    )
