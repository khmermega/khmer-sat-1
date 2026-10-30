import type { Status } from "../api";
import { MODE_STYLE, utcTime } from "../format";
import type { WsState } from "../useMission";
import { Button } from "./Panel";

interface Props {
  status: Status | null;
  ws: WsState;
  role: string | null;
  onLogin: () => void;
  onLogout: () => void;
  onTimeScale: (s: number) => void;
}

function Dot({ ok, warn, label, testId }: { ok: boolean; warn?: boolean; label: string; testId?: string }) {
  const c = ok ? "bg-ok" : warn ? "bg-warn" : "bg-crit";
  return (
    <span data-testid={testId} className="inline-flex items-center gap-1.5 text-[11px] text-ink-2">
      <span className={`h-1.5 w-1.5 rounded-full ${c} ${ok ? "" : "blink"}`} />
      {label}
    </span>
  );
}

function Logo() {
  return (
    <svg viewBox="0 0 40 40" className="h-9 w-9 shrink-0" aria-hidden>
      <defs>
        <linearGradient id="lg" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#f5b301" />
          <stop offset="1" stopColor="#d97706" />
        </linearGradient>
      </defs>
      <circle cx="20" cy="20" r="18.5" fill="none" stroke="#1e2a42" strokeWidth="1" />
      <ellipse cx="20" cy="20" rx="18" ry="7" fill="none" stroke="#38bdf8" strokeOpacity=".45" strokeWidth="1" transform="rotate(-25 20 20)" />
      {/* stylised Angkor tower silhouette doubling as the 3U bus */}
      <path d="M16 30V17l4-6 4 6v13z" fill="url(#lg)" />
      <path d="M18 30v-7h4v7" fill="#05080f" />
      <rect x="8" y="19" width="7" height="6" rx="1" fill="#38bdf8" />
      <rect x="25" y="19" width="7" height="6" rx="1" fill="#38bdf8" />
    </svg>
  );
}

export function TopBar({ status, ws, role, onLogin, onLogout, onTimeScale }: Props) {
  const mode = status?.onboard?.mode ?? status?.telemetry?.mode ?? null;
  const ms = mode ? MODE_STYLE[mode] : null;
  const sim = status?.gs_mode !== "HARDWARE";
  const age = status?.link.telemetry_age_s;
  const scale = status?.sim?.time_scale ?? 1;

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-deck/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5 lg:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <Logo />
          <div className="min-w-0">
            <div className="flex items-baseline gap-2">
              <h1 className="text-lg font-bold tracking-[0.12em] text-ink">
                KHMER-SAT <span className="text-gold">1</span>
              </h1>
              <span className="hidden text-[11px] uppercase tracking-[0.2em] text-ink-3 sm:inline">Mission Control</span>
            </div>
            <p className="truncate text-[11px] text-ink-3">Cambodian Earth Observation 3U CubeSat · engineering prototype · not flight qualified</p>
          </div>
        </div>

        <div
          data-testid="gs-mode"
          className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-bold tracking-[0.2em] ring-1 ring-inset ${
            sim ? "bg-gold/10 text-gold ring-gold/50" : "bg-crit/10 text-crit ring-crit/60"
          }`}
          title={sim ? "All telemetry, orbit and imagery shown are SIMULATED" : "Connected to physical hardware"}
        >
          <span className={`h-2 w-2 rounded-full ${sim ? "bg-gold" : "bg-crit"} blink`} />
          {sim ? "SIMULATION" : "HARDWARE"}
        </div>

        {ms && mode && (
          <div data-testid="sat-mode" className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold tracking-[0.15em] ring-1 ring-inset ${ms.bg} ${ms.text} ${ms.ring}`}>
            <span className={`h-2 w-2 rounded-full ${ms.dot}`} />
            {mode}
          </div>
        )}

        <div className="flex flex-col leading-tight">
          <span className="text-[10px] uppercase tracking-[0.18em] text-ink-3">{sim ? "Sim time (UTC)" : "UTC"}</span>
          <span className="font-mono text-sm tabular text-ink">{utcTime(status?.sim?.utc ?? status?.telemetry?.utc, true)}</span>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-2">
          <Dot testId="ws-state" ok={ws === "open"} warn={ws === "connecting"} label={ws === "open" ? "Stream" : ws === "connecting" ? "Connecting" : "Stream lost"} />
          <Dot ok={!!status?.link.up} label={status?.link.up ? "Link up" : "Link down"} />
          <Dot ok={age != null && age < 10} warn={age != null && age < 60} label={age == null ? "No TM" : `TM ${age.toFixed(0)}s`} />
          <Dot ok={!!status?.database.ok} label={status?.database.ok ? "DB" : "DB outage"} />

          {sim && (
            <div className="flex items-center gap-1 rounded-lg bg-panel p-0.5 ring-1 ring-line" title="Simulation time acceleration (operator)">
              {[1, 10, 60].map((s) => (
                <button
                  key={s}
                  disabled={!role}
                  onClick={() => onTimeScale(s)}
                  className={`rounded-md px-2 py-1 font-mono text-[11px] transition disabled:cursor-not-allowed disabled:opacity-40 ${
                    Math.abs(scale - s) < 0.01 ? "bg-sky/20 text-sky" : "text-ink-2 hover:text-ink"
                  }`}
                >
                  {s}×
                </button>
              ))}
            </div>
          )}

          {role ? (
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-ok/10 px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-ok ring-1 ring-ok/30">{role}</span>
              <Button variant="ghost" onClick={onLogout}>
                Sign out
              </Button>
            </div>
          ) : (
            <Button variant="primary" onClick={onLogin}>
              Operator sign-in
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}
