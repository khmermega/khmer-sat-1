import type { Housekeeping, Status } from "../api";
import { bytes, fmt } from "../format";

type Level = "ok" | "warn" | "crit" | "idle";

const LEVEL: Record<Level, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  crit: "bg-crit",
  idle: "bg-ink-3",
};

function Tile({ label, value, unit, sub, level = "idle", bar, testId }: { label: string; value: string; unit?: string; sub?: string; level?: Level; bar?: number; testId?: string }) {
  return (
    <div data-testid={testId} className="relative overflow-hidden rounded-xl border border-line bg-panel/90 px-4 py-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-3">{label}</span>
        <span className={`h-1.5 w-1.5 rounded-full ${LEVEL[level]}`} />
      </div>
      <div className="mt-1.5 flex items-baseline gap-1">
        <span className="font-mono text-2xl font-semibold tabular text-ink">{value}</span>
        {unit && <span className="text-xs text-ink-3">{unit}</span>}
      </div>
      {sub && <div className="mt-0.5 truncate font-mono text-[11px] tabular text-ink-3">{sub}</div>}
      {bar !== undefined && (
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-line">
          <div className={`h-full rounded-full ${LEVEL[level]} transition-[width] duration-700`} style={{ width: `${Math.max(0, Math.min(100, bar))}%` }} />
        </div>
      )}
    </div>
  );
}

function band(v: number | undefined, warn: number, crit: number, inverse = false): Level {
  if (v === undefined) return "idle";
  if (inverse) return v < crit ? "crit" : v < warn ? "warn" : "ok";
  return v > crit ? "crit" : v > warn ? "warn" : "ok";
}

export function KpiTiles({ hk, status }: { hk: Housekeeping | null | undefined; status: Status | null }) {
  const p = hk?.power;
  const t = hk?.thermal;
  const s = hk?.storage;
  const used = s ? (100 * s.used_bytes) / s.capacity_bytes : undefined;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
      <Tile testId="kpi-soc" label="Battery SoC" value={fmt(p?.soc_pct, 1)} unit="%" sub={p ? `${p.battery_v.toFixed(2)} V · ${p.battery_a >= 0 ? "+" : ""}${p.battery_a.toFixed(2)} A` : undefined} level={band(p?.soc_pct, 45, 30, true)} bar={p?.soc_pct} />
      <Tile label="Solar / Load" value={fmt(p?.solar_w, 1)} unit={`W / ${fmt(p?.load_w, 1)} W`} sub={p ? `net ${(p.solar_w - p.load_w).toFixed(2)} W` : undefined} level={p ? (p.solar_w >= p.load_w ? "ok" : "warn") : "idle"} />
      <Tile label="CPU temp" value={fmt(t?.cpu_c, 1)} unit="°C" sub={hk ? `load ${hk.cpu_load_pct.toFixed(0)}%` : undefined} level={band(t?.cpu_c, 60, 75)} />
      <Tile label="Payload temp" value={fmt(t?.payload_c, 1)} unit="°C" sub="limits −10…45 °C" level={t ? (t.payload_c > 45 || t.payload_c < -10 ? "crit" : t.payload_c > 38 ? "warn" : "ok") : "idle"} />
      <Tile label="Battery temp" value={fmt(t?.battery_c, 1)} unit="°C" sub={t ? `panel ${t.panel_c.toFixed(1)} °C` : undefined} level={t ? (t.battery_c < 0 || t.battery_c > 45 ? "crit" : "ok") : "idle"} />
      <Tile label="GNSS" value={hk ? (hk.gnss.fix ? "FIX" : "NO FIX") : "—"} sub={hk ? `${hk.gnss.sats} sats` : undefined} level={hk ? (hk.gnss.fix ? "ok" : "warn") : "idle"} />
      <Tile label="Storage" value={fmt(used, 1)} unit="%" sub={s ? `${bytes(s.used_bytes)} · ${s.images_stored} img · ${s.downlink_queue} queued` : undefined} level={band(used, 80, 95)} bar={used} />
      <Tile
        label="OBC"
        value={hk ? `#${hk.boot_count}` : "—"}
        unit="boot"
        sub={hk ? `up ${Math.floor(hk.uptime_s)} s · WDT ${status?.onboard?.watchdog_resets ?? 0}` : undefined}
        level={hk ? (hk.faults.filter((f) => f !== "GNSS_NO_FIX").length ? "warn" : "ok") : "idle"}
      />
    </div>
  );
}
