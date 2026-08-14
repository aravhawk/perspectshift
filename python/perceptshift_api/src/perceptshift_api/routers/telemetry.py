"""Telemetry REST and WebSocket endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from perceptshift_api.dependencies import DbDep, HubDep, RosDep
from perceptshift_api.models import SwitchEventRecord
from perceptshift_api.schemas import (
    SwitchEvent,
    TelemetryMetrics,
    TelemetryRecent,
    UnavailableField,
)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/recent", response_model=TelemetryRecent)
async def telemetry_recent(hub: HubDep, limit: int = 100) -> TelemetryRecent:
    clamped = max(1, min(limit, 500))
    return TelemetryRecent(events=hub.recent(clamped), dropped_event_count=hub.dropped_event_count)


@router.get("/switches", response_model=list[SwitchEvent])
def telemetry_switches(db: DbDep, hub: HubDep, limit: int = 100) -> list[SwitchEvent]:
    clamped = max(1, min(limit, 500))
    rows = db.scalars(
        select(SwitchEventRecord).order_by(SwitchEventRecord.sequence.desc()).limit(clamped)
    ).all()
    if rows:
        events: list[SwitchEvent] = []
        for row in reversed(rows):
            evidence: dict = {}
            if row.evidence_json:
                try:
                    evidence = json.loads(row.evidence_json)
                except json.JSONDecodeError:
                    evidence = {}
            events.append(
                SwitchEvent(
                    timestamp=row.created_at,
                    from_profile=row.from_profile,
                    to_profile=row.to_profile,
                    reason=row.reason,
                    sequence=row.sequence,
                    evidence=evidence,
                    manual=row.manual,
                )
            )
        return events

    # Fall back to in-memory telemetry switch events.
    live: list[SwitchEvent] = []
    for item in hub.recent(clamped):
        if item.get("event_type") != "switch_event":
            continue
        payload = item.get("payload") or {}
        live.append(
            SwitchEvent(
                timestamp=item["server_timestamp"],
                from_profile=payload.get("from_profile"),
                to_profile=payload.get("to_profile"),
                reason=payload.get("reason"),
                sequence=int(item["sequence_number"]),
                evidence=payload.get("evidence") or {},
                manual=bool(payload.get("manual", False)),
            )
        )
    return live


@router.get("/metrics", response_model=TelemetryMetrics)
def telemetry_metrics(hub: HubDep, ros: RosDep) -> TelemetryMetrics:
    events = [e for e in hub.recent(500) if e.get("event_type") == "inference_trace_summary"]
    if not events:
        unavailable = {
            "metrics": UnavailableField(
                reason_code="TELEMETRY_EMPTY",
                message="No inference telemetry has been received",
            )
        }
        if not ros.runtime_status().connected:
            unavailable["runtime"] = UnavailableField(
                reason_code=ros.state.reason_code,
                message=ros.state.message,
            )
        return TelemetryMetrics(
            sample_count=0,
            dropped_event_count=hub.dropped_event_count,
            unavailable=unavailable,
        )

    durations: list[float] = []
    misses = 0
    for event in events:
        payload = event.get("payload") or {}
        total = payload.get("total_ms")
        if isinstance(total, (int, float)):
            durations.append(float(total))
        if payload.get("deadline_miss"):
            misses += 1
    durations.sort()
    p50 = durations[len(durations) // 2] if durations else None
    p99 = durations[int(len(durations) * 0.99)] if durations else None
    return TelemetryMetrics(
        sample_count=len(durations),
        p50_ms=p50,
        p99_ms=p99,
        deadline_misses=misses,
        dropped_event_count=hub.dropped_event_count,
    )


@router.websocket("/stream")
async def telemetry_stream(websocket: WebSocket) -> None:
    hub = websocket.app.state.telemetry_hub
    try:
        sub = await hub.subscribe()
    except RuntimeError:
        await websocket.close(code=1013, reason="client limit reached")
        return

    await websocket.accept()
    await hub.emit_connection_status("connected", {"client_id": sub.client_id})
    try:
        from perceptshift_api.telemetry import utc_now_iso

        recent = hub.recent(1)
        hello = {
            "schema_version": "1.0",
            "document_type": "perceptshift.telemetry_event",
            "event_type": "connection_status",
            "sequence_number": 0,
            "server_timestamp": recent[-1]["server_timestamp"] if recent else utc_now_iso(),
            "trace_id": None,
            "payload": {
                "status": "subscribed",
                "client_id": sub.client_id,
                "queue_size": sub.queue.maxsize,
            },
            "dropped_event_count": hub.dropped_event_count,
        }
        await websocket.send_json(hello)

        while True:
            event = await sub.queue.get()
            payload = event.to_dict()
            payload["dropped_event_count"] = hub.dropped_event_count + sub.dropped
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(sub.client_id)
