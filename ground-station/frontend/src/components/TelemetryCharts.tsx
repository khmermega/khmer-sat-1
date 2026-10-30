import { useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Housekeeping } from "../api";
import { utcTime } from "../format";
import { Panel } from "./Panel";

type Tab = "power" | "thermal" | "orbit" | "attitude";

interface Series {
  key: string;
  name: string;
  color: string;
  axis?: "left" | "right";
  area?: boolean;
}

const TABS: Record<Tab, { label: string; series: Series[]; left: string; right?: string; refs?: { y: number; label: string; color: string; axis?: "left" | "right" }[] }> = {
  power: {
    label: "Power",
    left: "%",
    right: "W",
    series: [
      { key: "soc", name: "SoC %", color: "#34d399", area: true },
      { key: "solar", name: "Solar W", color: "#f5b301", axis: "right" },
      { key: "load", name: "Load W", color: "#f87171", axis: "right" },
    ],
    refs: [{ y: 30, label: "SAFE 30%", color: "#f87171" }],
  },
  thermal: {
    label: "Thermal",
    left: "°C",
    series: [
      { key: "cpu", name: "CPU", color: "#f87171" },
      { key: "payload", name: "Payload", color: "#38bdf8" },
      { key: "battery", name: "Battery", color: "#34d399" },
      { key: "panel", name: "Panel", color: "#a78bfa" },
    ],
    refs: [{ y: 45, label: "payload max", color: "#fbbf24" }],
  },
  orbit: {
    label: "Orbit & link",
    left: "°",
    right: "km",
    series: [
      { key: "el", name: "GS elevation °", color: "#38bdf8", area: true },
      { key: "alt", name: "Altitude km", color: "#f5b301", axis: "right" },
    ],
    refs: [{ y: 10, label: "mask 10°", color: "#38bdf8" }],
  },
  attitude: {
    label: "Attitude",
    left: "°/s",
    right: "V",
    series: [
      { key: "wx", name: "ωx", color: "#f87171" },
      { key: "wy", name: "ωy", color: "#34d399" },
      { key: "wz", name: "ωz", color: "#38bdf8" },
      { key: "volt", name: "Battery V", color: "#a78bfa", axis: "right" },
    ],
  },
};

export function TelemetryCharts({ history }: { history: Housekeeping[] }) {
  const [tab, setTab] = useState<Tab>("power");
  const [span, setSpan] = useState(30);
  const data = useMemo(() => {
    if (!history.length) return [];
    const end = new Date(history[history.length - 1].utc).getTime();
    const start = end - span * 60_000;
    const pts = history.filter((h) => new Date(h.utc).getTime() >= start);
    const stride = Math.max(1, Math.floor(pts.length / 600));
    return pts
      .filter((_, i) => i % stride === 0)
      .map((h) => ({
        t: new Date(h.utc).getTime(),
        soc: h.power.soc_pct,
        solar: h.power.solar_w,
        load: h.power.load_w,
        volt: h.power.battery_v,
        cpu: h.thermal.cpu_c,
        payload: h.thermal.payload_c,
        battery: h.thermal.battery_c,
        panel: h.thermal.panel_c,
        el: Math.max(-5, h.orbit.gs_elevation_deg),
        alt: h.orbit.alt_km,
        wx: h.attitude.rate_dps[0],
        wy: h.attitude.rate_dps[1],
        wz: h.attitude.rate_dps[2],
      }));
  }, [history, span]);
  const cfg = TABS[tab];

  return (
    <Panel
      testId="charts"
      title="Telemetry trends"
      subtitle={`${data.length} samples · simulated housekeeping`}
      actions={
        <>
          <div className="flex rounded-lg bg-deck p-0.5 ring-1 ring-line">
            {(Object.keys(TABS) as Tab[]).map((k) => (
              <button key={k} onClick={() => setTab(k)} className={`rounded-md px-2 py-1 text-[11px] ${tab === k ? "bg-sky/20 text-sky" : "text-ink-2 hover:text-ink"}`}>
                {TABS[k].label}
              </button>
            ))}
          </div>
          <select value={span} onChange={(e) => setSpan(Number(e.target.value))} className="rounded-lg border border-line bg-deck px-2 py-1 text-[11px] text-ink-2 outline-none" aria-label="Time span">
            {[5, 15, 30, 90].map((m) => (
              <option key={m} value={m}>
                {m} min
              </option>
            ))}
          </select>
        </>
      }
    >
      <div className="h-[260px]">
        {data.length < 2 ? (
          <div className="flex h-full items-center justify-center text-xs text-ink-3">Waiting for telemetry…</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 6, right: 4, left: -12, bottom: 0 }}>
              <defs>
                {cfg.series.filter((s) => s.area).map((s) => (
                  <linearGradient key={s.key} id={`g-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor={s.color} stopOpacity={0.35} />
                    <stop offset="1" stopColor={s.color} stopOpacity={0} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid stroke="#1e2a42" strokeDasharray="2 4" vertical={false} />
              <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} scale="time" tickFormatter={(v) => utcTime(new Date(v).toISOString()).slice(0, 5)} stroke="#62728f" fontSize={10} tickLine={false} />
              <YAxis yAxisId="left" stroke="#62728f" fontSize={10} tickLine={false} axisLine={false} unit={cfg.left === "%" ? "" : ""} domain={["auto", "auto"]} />
              {cfg.right && <YAxis yAxisId="right" orientation="right" stroke="#62728f" fontSize={10} tickLine={false} axisLine={false} domain={["auto", "auto"]} />}
              <Tooltip
                contentStyle={{ background: "#0a101c", border: "1px solid #2a3a5a", borderRadius: 8, fontSize: 11 }}
                labelFormatter={(v) => utcTime(new Date(Number(v)).toISOString(), true)}
                formatter={(v) => (typeof v === "number" ? v.toFixed(2) : String(v))}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: "#9aabc6" }} iconType="plainline" />
              {cfg.refs?.map((r) => (
                <ReferenceLine key={r.label} yAxisId={r.axis ?? "left"} y={r.y} stroke={r.color} strokeDasharray="4 4" strokeOpacity={0.6} label={{ value: r.label, fill: r.color, fontSize: 10, position: "insideTopLeft" }} />
              ))}
              {cfg.series.map((s) =>
                s.area ? (
                  <Area key={s.key} yAxisId={s.axis ?? "left"} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} fill={`url(#g-${s.key})`} strokeWidth={1.6} dot={false} isAnimationActive={false} />
                ) : (
                  <Line key={s.key} yAxisId={s.axis ?? "left"} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={1.4} dot={false} isAnimationActive={false} />
                ),
              )}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </Panel>
  );
}
