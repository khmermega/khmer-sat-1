import { useMemo, useState } from "react";
import { feature } from "topojson-client";
import type { Feature, FeatureCollection, Geometry, Position } from "geojson";
import type { Topology } from "topojson-specification";
import worldData from "world-atlas/countries-110m.json";
import type { Status, TrackPoint } from "../api";
import { fmt, utcTime } from "../format";
import { Panel } from "./Panel";

const W = 1000;
const H = 500;
const RE = 6378.137;
const CAMBODIA_ISO = "116";

const px = (lon: number) => ((lon + 180) / 360) * W;
const py = (lat: number) => ((90 - lat) / 180) * H;

const VIEWS = {
  global: { label: "Global", box: [0, 0, W, H] },
  region: { label: "SE Asia", box: [px(78), py(32), px(132) - px(78), py(-10) - py(32)] },
} as const;

function ringPath(ring: Position[]): string {
  let d = "";
  let prev: number | null = null;
  for (const [lon, lat] of ring) {
    const jump = prev !== null && Math.abs(lon - prev) > 180;
    d += `${d === "" || jump ? "M" : "L"}${px(lon).toFixed(1)},${py(lat).toFixed(1)}`;
    prev = lon;
  }
  return d + "Z";
}

function geomPath(g: Geometry): string {
  if (g.type === "Polygon") return g.coordinates.map(ringPath).join("");
  if (g.type === "MultiPolygon") return g.coordinates.flatMap((p) => p.map(ringPath)).join("");
  return "";
}

/** Split a lon/lat polyline wherever it crosses the antimeridian. */
function polylines(pts: { lat: number; lon: number }[]): string[] {
  const out: string[] = [];
  let cur = "";
  let prev: number | null = null;
  for (const p of pts) {
    if (prev !== null && Math.abs(p.lon - prev) > 180) {
      out.push(cur);
      cur = "";
    }
    cur += `${cur ? "L" : "M"}${px(p.lon).toFixed(1)},${py(p.lat).toFixed(1)}`;
    prev = p.lon;
  }
  if (cur) out.push(cur);
  return out;
}

/** Small circle of angular radius `rad` around (lat, lon): visibility footprint. */
function smallCircle(lat: number, lon: number, rad: number): { lat: number; lon: number }[] {
  const φ1 = (lat * Math.PI) / 180;
  const λ1 = (lon * Math.PI) / 180;
  const pts = [];
  for (let b = 0; b <= 360; b += 4) {
    const θ = (b * Math.PI) / 180;
    const φ2 = Math.asin(Math.sin(φ1) * Math.cos(rad) + Math.cos(φ1) * Math.sin(rad) * Math.cos(θ));
    const λ2 = λ1 + Math.atan2(Math.sin(θ) * Math.sin(rad) * Math.cos(φ1), Math.cos(rad) - Math.sin(φ1) * Math.sin(φ2));
    pts.push({ lat: (φ2 * 180) / Math.PI, lon: ((((λ2 * 180) / Math.PI + 540) % 360) - 180) });
  }
  return pts;
}

/** Earth central angle of the visibility footprint for a given altitude and min elevation. */
function footprintRad(altKm: number, minElDeg: number): number {
  const ε = (minElDeg * Math.PI) / 180;
  return Math.acos((RE / (RE + altKm)) * Math.cos(ε)) - ε;
}

/** Approximate night-side polygon (low-precision subsolar point; display only). */
function nightPath(iso: string): string {
  const d = new Date(iso);
  const n = d.getTime() / 86400000 + 2440587.5 - 2451545.0;
  const L = (280.46 + 0.9856474 * n) % 360;
  const g = ((357.528 + 0.9856003 * n) % 360) * (Math.PI / 180);
  const λ = (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * (Math.PI / 180);
  const ε = 23.439 * (Math.PI / 180);
  const dec = Math.asin(Math.sin(ε) * Math.sin(λ));
  const ra = Math.atan2(Math.cos(ε) * Math.sin(λ), Math.cos(λ));
  const gmst = ((280.46061837 + 360.98564736629 * n) % 360) * (Math.PI / 180);
  const subLon = ((((ra - gmst) * 180) / Math.PI + 540) % 360) - 180;
  let d0 = "";
  for (let lon = -180; lon <= 180; lon += 2) {
    const h = ((lon - subLon) * Math.PI) / 180;
    const lat = (Math.atan(-Math.cos(h) / Math.tan(dec || 1e-6)) * 180) / Math.PI;
    d0 += `${d0 ? "L" : "M"}${px(lon).toFixed(1)},${py(lat).toFixed(1)}`;
  }
  const poleY = dec > 0 ? H : 0; // night pole is opposite the sun's hemisphere
  return `${d0}L${W},${poleY}L0,${poleY}Z`;
}

export function GroundTrackMap({ status, track, label }: { status: Status | null; track: TrackPoint[]; label: string }) {
  const [view, setView] = useState<keyof typeof VIEWS>("global");
  const countries = useMemo(() => {
    const topo = worldData as unknown as Topology;
    const fc = feature(topo, topo.objects.countries) as unknown as FeatureCollection;
    return fc.features.map((f: Feature) => ({ id: String(f.id), d: geomPath(f.geometry) }));
  }, []);

  const hk = status?.telemetry;
  const gs = status?.ground_station;
  const nowIso = status?.sim?.utc ?? hk?.utc ?? new Date().toISOString();
  const now = new Date(nowIso).getTime();
  const past = track.filter((p) => new Date(p.utc).getTime() <= now);
  const future = track.filter((p) => new Date(p.utc).getTime() >= now);
  const alt = hk?.orbit.alt_km ?? 500;
  const fp = gs ? smallCircle(gs.lat_deg, gs.lon_deg, footprintRad(alt, gs.min_elevation_deg)) : [];
  const satFp = hk ? smallCircle(hk.orbit.lat_deg, hk.orbit.lon_deg, footprintRad(alt, 0)) : [];
  const box = VIEWS[view].box;
  const k = box[2] / W; // marker scale for zoomed view

  return (
    <Panel
      testId="ground-track"
      title="Orbit · Ground track"
      subtitle={<span className="text-gold/80">{label || "SYNTHETIC DEMO ORBIT"} · SGP4 · 50 min history / 100 min prediction</span>}
      actions={
        <div className="flex rounded-lg bg-deck p-0.5 ring-1 ring-line">
          {(Object.keys(VIEWS) as (keyof typeof VIEWS)[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`rounded-md px-2 py-1 text-[11px] ${view === v ? "bg-sky/20 text-sky" : "text-ink-2 hover:text-ink"}`}
            >
              {VIEWS[v].label}
            </button>
          ))}
        </div>
      }
      bodyClassName="p-0"
    >
      <div className="relative">
        <svg viewBox={box.join(" ")} className="block h-auto w-full rounded-b-xl bg-[#071223]" role="img" aria-label="Satellite ground track map">
          <defs>
            <radialGradient id="satGlow">
              <stop offset="0" stopColor="#f5b301" stopOpacity=".9" />
              <stop offset="1" stopColor="#f5b301" stopOpacity="0" />
            </radialGradient>
          </defs>
          {/* graticule */}
          {Array.from({ length: 13 }, (_, i) => -180 + i * 30).map((lon) => (
            <line key={`m${lon}`} x1={px(lon)} x2={px(lon)} y1={0} y2={H} stroke="#13233d" strokeWidth={0.6 * k} />
          ))}
          {Array.from({ length: 7 }, (_, i) => -90 + i * 30).map((lat) => (
            <line key={`p${lat}`} x1={0} x2={W} y1={py(lat)} y2={py(lat)} stroke={lat === 0 ? "#1d3557" : "#13233d"} strokeWidth={0.6 * k} />
          ))}
          {countries.map((c) => (
            <path
              key={c.id + c.d.length}
              d={c.d}
              fill={c.id === CAMBODIA_ISO ? "#f5b30133" : "#14233a"}
              stroke={c.id === CAMBODIA_ISO ? "#f5b301" : "#25395a"}
              strokeWidth={(c.id === CAMBODIA_ISO ? 1 : 0.5) * k}
            />
          ))}
          <path d={nightPath(nowIso)} fill="#000814" fillOpacity={0.45} />
          {/* satellite instantaneous horizon (0 deg elevation) */}
          {polylines(satFp).map((d, i) => (
            <path key={`sf${i}`} d={d} fill="none" stroke="#f5b301" strokeOpacity={0.25} strokeWidth={0.8 * k} />
          ))}
          {/* ground-station visibility mask (min elevation) */}
          {polylines(fp).map((d, i) => (
            <path key={`gf${i}`} d={d} fill="#38bdf8" fillOpacity={0.06} stroke="#38bdf8" strokeOpacity={0.6} strokeDasharray={`${3 * k} ${3 * k}`} strokeWidth={0.9 * k} />
          ))}
          {polylines(past).map((d, i) => (
            <path key={`p${i}`} d={d} fill="none" stroke="#38bdf8" strokeOpacity={0.85} strokeWidth={1.6 * k} />
          ))}
          {polylines(future).map((d, i) => (
            <path key={`f${i}`} d={d} fill="none" stroke="#f5b301" strokeOpacity={0.7} strokeDasharray={`${5 * k} ${4 * k}`} strokeWidth={1.3 * k} />
          ))}
          {gs && (
            <g transform={`translate(${px(gs.lon_deg)},${py(gs.lat_deg)})`}>
              <path d={`M0,${-6 * k}L${5 * k},${4 * k}L${-5 * k},${4 * k}Z`} fill={status?.link.gs_visible ? "#34d399" : "#38bdf8"} stroke="#05080f" strokeWidth={0.8 * k} />
              <text x={7 * k} y={4 * k} fontSize={10 * k} fill="#9aabc6">
                {gs.name.replace(" (simulated)", "")}
              </text>
            </g>
          )}
          {hk && (
            <g transform={`translate(${px(hk.orbit.lon_deg)},${py(hk.orbit.lat_deg)})`}>
              <circle r={14 * k} fill="url(#satGlow)" />
              <circle r={6 * k} fill="none" stroke="#f5b301" strokeWidth={1.2 * k} className="pulse-ring" />
              <rect x={-3 * k} y={-3 * k} width={6 * k} height={6 * k} fill="#f5b301" stroke="#05080f" strokeWidth={0.8 * k} transform="rotate(45)" />
            </g>
          )}
        </svg>
        <div className="pointer-events-none absolute left-3 top-3 grid grid-cols-2 gap-x-5 gap-y-1 rounded-lg bg-void/75 px-3 py-2 font-mono text-[11px] tabular ring-1 ring-line backdrop-blur">
          <span className="text-ink-3">LAT</span>
          <span className="text-right text-ink">{fmt(hk?.orbit.lat_deg, 3, "°")}</span>
          <span className="text-ink-3">LON</span>
          <span className="text-right text-ink">{fmt(hk?.orbit.lon_deg, 3, "°")}</span>
          <span className="text-ink-3">ALT</span>
          <span className="text-right text-ink">{fmt(hk?.orbit.alt_km, 1, " km")}</span>
          <span className="text-ink-3">VEL</span>
          <span className="text-right text-ink">{fmt(hk?.orbit.speed_km_s, 3, " km/s")}</span>
          <span className="text-ink-3">SUN</span>
          <span className={`text-right ${hk?.orbit.sunlit ? "text-gold" : "text-ink-2"}`}>{hk ? (hk.orbit.sunlit ? "SUNLIT" : "ECLIPSE") : "—"}</span>
        </div>
        <div className="pointer-events-none absolute bottom-2 right-3 flex flex-wrap items-center gap-3 rounded-md bg-void/70 px-2 py-1 text-[10px] text-ink-3 ring-1 ring-line">
          <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-sky" />past</span>
          <span className="flex items-center gap-1"><span className="h-0.5 w-4 border-t border-dashed border-gold" />predicted</span>
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full border border-dashed border-sky" />GS mask ≥{gs?.min_elevation_deg ?? 10}°</span>
          <span>night shading approx. · {utcTime(nowIso)}</span>
        </div>
      </div>
    </Panel>
  );
}
