import type { PassItem, Status } from "../api";
import { bytes, duration, fmt, utcTime } from "../format";
import { Chip, Panel } from "./Panel";

function Stat({ label, value, tone = "text-ink" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-[11px] text-ink-3">{label}</span>
      <span className={`font-mono text-[11px] tabular ${tone}`}>{value}</span>
    </div>
  );
}

/** Polar sky plot of the satellite as seen from the ground station. */
function SkyPlot({ az, el, visible }: { az?: number; el?: number; visible?: boolean }) {
  const r = (e: number) => 44 * (1 - Math.max(0, e) / 90);
  const show = az !== undefined && el !== undefined && el > -5;
  const x = show ? 50 + r(el!) * Math.sin((az! * Math.PI) / 180) : 0;
  const y = show ? 50 - r(el!) * Math.cos((az! * Math.PI) / 180) : 0;
  return (
    <svg viewBox="0 0 100 100" className="h-28 w-28 shrink-0">
      {[0, 30, 60].map((e) => (
        <circle key={e} cx="50" cy="50" r={r(e)} fill="none" stroke="#1e2a42" strokeWidth=".6" />
      ))}
      <circle cx="50" cy="50" r={r(10)} fill="none" stroke="#38bdf8" strokeOpacity=".5" strokeDasharray="2 2" strokeWidth=".6" />
      <line x1="50" y1="6" x2="50" y2="94" stroke="#1e2a42" strokeWidth=".5" />
      <line x1="6" y1="50" x2="94" y2="50" stroke="#1e2a42" strokeWidth=".5" />
      <text x="50" y="5" fontSize="5" textAnchor="middle" fill="#62728f">N</text>
      <text x="97" y="52" fontSize="5" textAnchor="middle" fill="#62728f">E</text>
      {show && <circle cx={x} cy={y} r="3" fill={visible ? "#34d399" : "#f5b301"} stroke="#05080f" strokeWidth=".8" />}
    </svg>
  );
}

export function LinkPanel({ status, passes, role, onLinkMode }: { status: Status | null; passes: PassItem[]; role: string | null; onLinkMode: (m: string) => void }) {
  const l = status?.link;
  const now = new Date(status?.sim?.utc ?? Date.now()).getTime();
  const upcoming = passes.filter((p) => new Date(p.los).getTime() > now).slice(0, 4);
  const next = upcoming[0];
  const inPass = next && new Date(next.aos).getTime() <= now;
  const dl = l?.downlink;
  const loss = dl && dl.sent ? (100 * dl.dropped) / dl.sent : 0;
  const linkMode = status?.sim?.link_mode;

  return (
    <Panel
      testId="link"
      title="Ground link"
      subtitle={status?.ground_station?.name ?? "—"}
      actions={
        <Chip className={l?.up ? "text-ok bg-ok/10 ring-ok/30" : "text-crit bg-crit/10 ring-crit/30"}>{l?.up ? "LINK UP" : "NO LINK"}</Chip>
      }
    >
      <div className="flex gap-4">
        <SkyPlot az={l?.azimuth_deg} el={l?.elevation_deg} visible={l?.gs_visible} />
        <div className="min-w-0 flex-1 divide-y divide-line/60">
          <Stat label="Elevation" value={fmt(l?.elevation_deg, 1, "°")} tone={l?.gs_visible ? "text-ok" : "text-ink"} />
          <Stat label="Azimuth" value={fmt(l?.azimuth_deg, 1, "°")} />
          <Stat label="Slant range" value={fmt(l?.range_km, 0, " km")} />
          <Stat label="Last frame" value={utcTime(l?.last_rx_utc)} />
        </div>
      </div>

      <div className="mt-3 rounded-lg bg-deck/60 p-3 ring-1 ring-line">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wider text-ink-3">Link mode</span>
          <div className="flex rounded-md bg-panel p-0.5 ring-1 ring-line">
            {["bench", "orbital"].map((m) => (
              <button
                key={m}
                disabled={!role}
                onClick={() => onLinkMode(m)}
                className={`rounded px-2 py-0.5 text-[11px] disabled:opacity-40 ${linkMode === m ? "bg-sky/20 text-sky" : "text-ink-2"}`}
                title={m === "bench" ? "Wired/simulated bench link, always connected" : "Link only while the station sees the satellite"}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
        <p className="mt-1.5 text-[10px] leading-relaxed text-ink-3">Software channel only. No RF is transmitted — RF requires licensing &amp; authorization.</p>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-4">
        <Stat label="DL frames" value={`${dl?.delivered ?? 0}`} />
        <Stat label="DL volume" value={bytes(dl?.bytes_delivered ?? 0)} />
        <Stat label="Dropped" value={`${dl?.dropped ?? 0} (${loss.toFixed(1)}%)`} tone={loss > 0 ? "text-warn" : "text-ink"} />
        <Stat label="CRC rejects" value={`${l?.ground?.rx_crc_errors ?? 0}`} tone={(l?.ground?.rx_crc_errors ?? 0) > 0 ? "text-warn" : "text-ink"} />
        <Stat label="Duplicates" value={`${l?.ground?.rx_duplicates ?? 0}`} />
        <Stat label="UL commands" value={`${l?.ground?.tx_frames ?? 0}`} />
      </div>

      <div className="mt-3">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-3">Predicted passes (24 h)</span>
          {next && (
            <span className={`font-mono text-[11px] ${inPass ? "text-ok" : "text-sky"}`}>
              {inPass ? `LOS in ${duration((new Date(next.los).getTime() - now) / 1000)}` : `AOS in ${duration((new Date(next.aos).getTime() - now) / 1000)}`}
            </span>
          )}
        </div>
        <div className="space-y-1">
          {upcoming.length === 0 && <div className="text-[11px] text-ink-3">No passes above mask in the next 24 h</div>}
          {upcoming.map((p) => (
            <div key={p.aos} className="flex items-center justify-between rounded-md bg-deck/60 px-2 py-1 font-mono text-[11px] tabular ring-1 ring-line">
              <span className="text-ink">{utcTime(p.aos)}</span>
              <span className="text-ink-3">{duration(p.duration_s)}</span>
              <span className={p.max_elevation_deg > 45 ? "text-ok" : "text-ink-2"}>max {p.max_elevation_deg.toFixed(0)}°</span>
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}
