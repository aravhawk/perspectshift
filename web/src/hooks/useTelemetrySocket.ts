import { useCallback, useEffect, useRef, useState } from "react";
import type { TelemetryEvent } from "@/types/api";

export type Clock = () => number;

const defaultClock: Clock = () => Date.now();

export type UseTelemetrySocketOptions = {
  url?: string;
  enabled?: boolean;
  maxEvents?: number;
  clock?: Clock;
  reconnectBaseMs?: number;
  reconnectMaxMs?: number;
};

export type TelemetrySocketState = {
  connected: boolean;
  events: TelemetryEvent[];
  lastSequence: number | null;
  sequenceGaps: number;
  droppedEventCount: number;
  error: string | null;
};

export function useTelemetrySocket(options: UseTelemetrySocketOptions = {}) {
  const {
    url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/v1/telemetry/stream`,
    enabled = true,
    maxEvents = 256,
    clock = defaultClock,
    reconnectBaseMs = 500,
    reconnectMaxMs = 8000,
  } = options;

  const [state, setState] = useState<TelemetrySocketState>({
    connected: false,
    events: [],
    lastSequence: null,
    sequenceGaps: 0,
    droppedEventCount: 0,
    error: null,
  });

  const cancelled = useRef(false);
  const attempt = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);

  const reset = useCallback(() => {
    setState({
      connected: false,
      events: [],
      lastSequence: null,
      sequenceGaps: 0,
      droppedEventCount: 0,
      error: null,
    });
  }, []);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    cancelled.current = false;
    let timer: number | undefined;

    const connect = () => {
      if (cancelled.current) {
        return;
      }
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attempt.current = 0;
        setState((prev) => ({ ...prev, connected: true, error: null }));
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(String(event.data)) as TelemetryEvent;
          setState((prev) => {
            let gaps = prev.sequenceGaps;
            if (
              prev.lastSequence !== null &&
              payload.sequence_number > prev.lastSequence + 1
            ) {
              gaps += 1;
            }
            const nextEvents = [...prev.events, payload].slice(-maxEvents);
            return {
              ...prev,
              events: nextEvents,
              lastSequence: payload.sequence_number,
              sequenceGaps: gaps,
              droppedEventCount: payload.dropped_event_count ?? prev.droppedEventCount,
            };
          });
        } catch {
          setState((prev) => ({
            ...prev,
            error: "Malformed telemetry frame",
          }));
        }
      };

      ws.onerror = () => {
        setState((prev) => ({
          ...prev,
          error: "WebSocket error",
          connected: false,
        }));
      };

      ws.onclose = () => {
        setState((prev) => ({ ...prev, connected: false }));
        if (cancelled.current) {
          return;
        }
        const delay = Math.min(
          reconnectMaxMs,
          reconnectBaseMs * 2 ** attempt.current,
        );
        attempt.current += 1;
        timer = window.setTimeout(connect, delay);
        void clock();
      };
    };

    connect();

    return () => {
      cancelled.current = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [enabled, url, maxEvents, clock, reconnectBaseMs, reconnectMaxMs]);

  return { ...state, reset };
}
