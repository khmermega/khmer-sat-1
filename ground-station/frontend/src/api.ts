// Typed client for the KHMER-SAT 1 ground-station API.

export type Mode = "BOOT" | "NOMINAL" | "IMAGING" | "DOWNLINK" | "SAFE" | "FAULT";
export type Severity = "INFO" | "WARNING" | "CRITICAL";

export interface Housekeeping {
  utc: string;
  mode: Mode;
  uptime_s: number;
  boot_count: number;
  cpu_load_pct: number;
  orbit: {
    lat_deg: number;
    lon_deg: number;
    alt_km: number;
    speed_km_s: number;
    sunlit: boolean;
    gs_elevation_deg: number;
    gs_visible: boolean;
  };
  power: { soc_pct: number; battery_v: number; battery_a: number; solar_w: number; load_w: number };
  thermal: { cpu_c: number; payload_c: number; battery_c: number; panel_c: number };
  attitude: { q: number[]; rate_dps: number[]; mag_ut: number[] };
  gnss: { fix: boolean; sats: number; lat_deg: number | null; lon_deg: number | null; alt_km: number | null };
  storage: { used_bytes: number; capacity_bytes: number; images_stored: number; downlink_queue: number };
  faults: string[];
  last_cmd_seq: number | null;
  simulated: boolean;
}

export interface ChannelStats {
  sent: number;
  delivered: number;
  dropped: number;
  duplicated: number;
  corrupted: number;
  blocked: number;
  bytes_delivered: number;
}

export interface Status {
  gs_mode: "SIMULATION" | "HARDWARE";
  satellite?: { name: string; id: number; protocol_version: number };
  sim?: { utc: string; start_utc: string; time_scale: number; paused: boolean; link_mode: "bench" | "orbital"; elements_label: string };
  ground_station?: { name: string; lat_deg: number; lon_deg: number; alt_km: number; min_elevation_deg: number };
  link: {
    up: boolean;
    gs_visible?: boolean;
    elevation_deg?: number;
    azimuth_deg?: number;
    range_km?: number;
    last_rx_utc?: string | null;
    telemetry_age_s?: number | null;
    ground?: Record<string, number>;
    uplink?: ChannelStats;
    downlink?: ChannelStats;
    pending_image_reassembly?: number;
  };
  onboard?: {
    mode: Mode;
    downlink_queue: number;
    scheduled_captures: number;
    camera: { width: number; height: number; jpeg_quality: number };
    watchdog_resets: number;
    stats: Record<string, number>;
  };
  database: { ok: boolean; pending_writes?: number; dropped?: number };
  faults?: Record<string, number | boolean>;
  telemetry: Housekeeping | null;
}

export interface EventItem {
  id: string;
  utc: string;
  severity: Severity;
  origin: "space" | "ground";
  source: string;
  code: string;
  message: string;
  acknowledged: boolean;
  acknowledged_by: string | null;
}

export interface CommandItem {
  id: string;
  created_utc: string;
  type: string;
  args: Record<string, unknown>;
  operator: string;
  automatic: boolean;
  critical: boolean;
  status: "SENT" | "ACCEPTED" | "REJECTED" | "COMPLETED" | "FAILED" | "TIMEOUT";
  seq: number | null;
  reason: string;
  ack_utc: string | null;
  detail: Record<string, unknown>;
}

export interface ImageItem {
  id: string;
  captured_utc: string;
  received_utc: string;
  source: "SIMULATED_ORBITAL" | "GROUND_TEST_HARDWARE" | "MOCK_SAMPLE";
  camera: string;
  width: number;
  height: number;
  size_bytes: number;
  sha256: string;
  verified: boolean;
  meta: Record<string, unknown>;
}

export interface TrackPoint {
  utc: string;
  lat: number;
  lon: number;
  alt_km: number;
  sunlit: boolean;
}

export interface PassItem {
  aos: string;
  los: string;
  tca: string;
  max_elevation_deg: number;
  duration_s: number;
}

export interface CatalogEntry {
  type: string;
  args: Record<string, unknown>;
  description: string;
  critical?: boolean;
}

const TOKEN_KEY = "ks1.operatorToken";

export function getToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable - token lives only in memory for this page */
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}, auth = false): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) {
    const t = getToken();
    if (t) headers.Authorization = `Bearer ${t}`;
  }
  const res = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  status: () => request<Status>("/api/status"),
  history: (minutes: number) =>
    request<{ degraded: boolean; count: number; points: Housekeeping[] }>(`/api/telemetry/history?minutes=${minutes}&max_points=900`),
  track: () => request<{ now_utc: string; label: string; points: TrackPoint[] }>("/api/orbit/track?back_min=50&ahead_min=100&step_s=30"),
  passes: () => request<{ station: string; label: string; passes: PassItem[] }>("/api/orbit/passes?hours=24"),
  elements: () => request<Record<string, unknown>>("/api/orbit/elements"),
  events: () => request<{ degraded: boolean; events: EventItem[] }>("/api/events?limit=300"),
  commands: () => request<{ degraded: boolean; commands: CommandItem[] }>("/api/commands?limit=200"),
  images: () => request<{ degraded: boolean; images: ImageItem[] }>("/api/images?limit=200"),
  catalog: () => request<CatalogEntry[]>("/api/commands/catalog"),
  whoami: () => request<{ name: string; role: "operator" | "admin" }>("/api/auth/whoami", {}, true),
  send: (type: string, args: Record<string, unknown>) =>
    request<CommandItem>("/api/commands", { method: "POST", body: JSON.stringify({ type, args }) }, true),
  arm: (type: string, args: Record<string, unknown>) =>
    request<{ arm_id: string; type: string; expires_in_s: number }>("/api/commands/arm", { method: "POST", body: JSON.stringify({ type, args }) }, true),
  execute: (arm_id: string) => request<CommandItem>("/api/commands/execute", { method: "POST", body: JSON.stringify({ arm_id }) }, true),
  ackEvent: (id: string) => request<EventItem>(`/api/events/${id}/ack`, { method: "POST" }, true),
  simControl: (body: { time_scale?: number; paused?: boolean; link_mode?: string }) =>
    request<{ time_scale: number; paused: boolean; link_mode: string }>("/api/sim/control", { method: "POST", body: JSON.stringify(body) }, true),
  setFaults: (body: Record<string, unknown>) => request<Record<string, unknown>>("/api/sim/faults", { method: "POST", body: JSON.stringify(body) }, true),
};

export function wsUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws`;
}
