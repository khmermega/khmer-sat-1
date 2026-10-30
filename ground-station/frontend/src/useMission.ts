import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  wsUrl,
  type CommandItem,
  type EventItem,
  type Housekeeping,
  type ImageItem,
  type PassItem,
  type Status,
  type TrackPoint,
} from "./api";

const HISTORY_MIN = 90;
const MAX_HISTORY = 3000;

export type WsState = "connecting" | "open" | "closed";

export interface MissionData {
  status: Status | null;
  ws: WsState;
  history: Housekeeping[];
  events: EventItem[];
  commands: CommandItem[];
  images: ImageItem[];
  track: TrackPoint[];
  trackLabel: string;
  passes: PassItem[];
  refreshCommands: () => void;
  refreshEvents: () => void;
}

function upsert<T extends { id: string }>(list: T[], items: T[], key: (t: T) => string, max: number): T[] {
  if (!items.length) return list;
  const map = new Map(list.map((x) => [x.id, x]));
  for (const it of items) map.set(it.id, it);
  return [...map.values()].sort((a, b) => key(b).localeCompare(key(a))).slice(0, max);
}

/** Live mission state: REST bootstrap + WebSocket stream with automatic reconnect. */
export function useMission(): MissionData {
  const [status, setStatus] = useState<Status | null>(null);
  const [ws, setWs] = useState<WsState>("connecting");
  const [history, setHistory] = useState<Housekeeping[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [commands, setCommands] = useState<CommandItem[]>([]);
  const [images, setImages] = useState<ImageItem[]>([]);
  const [track, setTrack] = useState<TrackPoint[]>([]);
  const [trackLabel, setTrackLabel] = useState("");
  const [passes, setPasses] = useState<PassItem[]>([]);
  const lastHk = useRef<string>("");

  const refreshCommands = useCallback(() => {
    api.commands().then((r) => setCommands(r.commands)).catch(() => {});
  }, []);
  const refreshEvents = useCallback(() => {
    api.events().then((r) => setEvents(r.events)).catch(() => {});
  }, []);

  // Bootstrap history/lists, then keep slow-changing orbit products fresh.
  useEffect(() => {
    api.status().then(setStatus).catch(() => {});
    api.history(HISTORY_MIN).then((r) => {
      setHistory(r.points);
      lastHk.current = r.points.at(-1)?.utc ?? "";
    }).catch(() => {});
    refreshEvents();
    refreshCommands();
    api.images().then((r) => setImages(r.images)).catch(() => {});
    const loadOrbit = () => {
      api.track().then((r) => {
        setTrack(r.points);
        setTrackLabel(r.label);
      }).catch(() => {});
      api.passes().then((r) => setPasses(r.passes)).catch(() => {});
    };
    loadOrbit();
    const t = setInterval(loadOrbit, 20_000);
    return () => clearInterval(t);
  }, [refreshCommands, refreshEvents]);

  useEffect(() => {
    let sock: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    let backoff = 1000;

    const connect = () => {
      setWs("connecting");
      sock = new WebSocket(wsUrl());
      sock.onopen = () => {
        setWs("open");
        backoff = 1000;
      };
      sock.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.status) setStatus(msg.status as Status);
        const hk: Housekeeping | null = msg.status?.telemetry ?? null;
        if (hk && hk.utc !== lastHk.current) {
          lastHk.current = hk.utc;
          setHistory((h) => (h.length >= MAX_HISTORY ? [...h.slice(-MAX_HISTORY + 1), hk] : [...h, hk]));
        }
        if (msg.events?.length) setEvents((e) => upsert(e, msg.events as EventItem[], (x) => x.utc, 500));
        if (msg.commands?.length) setCommands((c) => upsert(c, msg.commands as CommandItem[], (x) => x.created_utc, 300));
        if (msg.images?.length) setImages((i) => upsert(i, msg.images as ImageItem[], (x) => x.captured_utc, 300));
      };
      sock.onclose = () => {
        setWs("closed");
        if (!closed) {
          retry = setTimeout(connect, backoff);
          backoff = Math.min(backoff * 2, 15_000);
        }
      };
      sock.onerror = () => sock?.close();
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      sock?.close();
    };
  }, []);

  return { status, ws, history, events, commands, images, track, trackLabel, passes, refreshCommands, refreshEvents };
}
