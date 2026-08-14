"""Bounded telemetry cache and WebSocket fan-out."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class TelemetryEvent:
    event_type: str
    payload: dict[str, Any]
    sequence_number: int
    server_timestamp: str
    trace_id: str | None = None
    dropped_event_count: int = 0
    schema_version: str = "1.0"
    document_type: str = "perceptshift.telemetry_event"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_type": self.document_type,
            "event_type": self.event_type,
            "sequence_number": self.sequence_number,
            "server_timestamp": self.server_timestamp,
            "trace_id": self.trace_id,
            "payload": self.payload,
            "dropped_event_count": self.dropped_event_count,
        }


@dataclass
class ClientSubscription:
    client_id: str
    queue: asyncio.Queue[TelemetryEvent]
    dropped: int = 0


@dataclass
class TelemetryHub:
    cache_size: int = 512
    queue_size: int = 64
    max_clients: int = 32
    _sequence: int = 0
    _dropped_total: int = 0
    _cache: deque[TelemetryEvent] = field(default_factory=deque)
    _clients: dict[str, ClientSubscription] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        self._cache = deque(maxlen=self.cache_size)

    @property
    def dropped_event_count(self) -> int:
        return self._dropped_total

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        items = list(self._cache)[-limit:]
        return [item.to_dict() for item in items]

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        trace_id: str | None = None,
    ) -> TelemetryEvent:
        async with self._lock:
            self._sequence += 1
            event = TelemetryEvent(
                event_type=event_type,
                payload=payload,
                sequence_number=self._sequence,
                server_timestamp=utc_now_iso(),
                trace_id=trace_id,
                dropped_event_count=self._dropped_total,
            )
            self._cache.append(event)
            stale_clients: list[str] = []
            for client_id, sub in self._clients.items():
                try:
                    sub.queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Drop oldest to make room (coalesce), count drop.
                    try:
                        _ = sub.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        sub.queue.put_nowait(event)
                    except asyncio.QueueFull:
                        stale_clients.append(client_id)
                        continue
                    sub.dropped += 1
                    self._dropped_total += 1
                    event.dropped_event_count = self._dropped_total
            for client_id in stale_clients:
                self._clients.pop(client_id, None)
            return event

    async def subscribe(self) -> ClientSubscription:
        async with self._lock:
            if len(self._clients) >= self.max_clients:
                raise RuntimeError("websocket_client_limit")
            client_id = str(uuid4())
            sub = ClientSubscription(
                client_id=client_id,
                queue=asyncio.Queue(maxsize=self.queue_size),
            )
            self._clients[client_id] = sub
            return sub

    async def unsubscribe(self, client_id: str) -> None:
        async with self._lock:
            self._clients.pop(client_id, None)

    async def emit_connection_status(
        self, status: str, detail: dict[str, Any] | None = None
    ) -> None:
        await self.publish(
            "connection_status",
            {"status": status, **(detail or {})},
        )
