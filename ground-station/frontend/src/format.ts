import type { Mode, Severity } from "./api";

export const fmt = (v: number | null | undefined, digits = 1, unit = ""): string =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${v.toFixed(digits)}${unit}`;

export function utcTime(iso: string | null | undefined, withDate = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const t = d.toISOString();
  return withDate ? `${t.slice(0, 10)} ${t.slice(11, 19)}Z` : `${t.slice(11, 19)}Z`;
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KiB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MiB`;
  return `${(n / 1024 ** 3).toFixed(2)} GiB`;
}

export function duration(s: number): string {
  if (s < 0) s = 0;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m ${String(sec).padStart(2, "0")}s`;
}

export const MODE_STYLE: Record<Mode, { text: string; bg: string; ring: string; dot: string }> = {
  BOOT: { text: "text-ink-2", bg: "bg-ink-3/15", ring: "ring-ink-3/40", dot: "bg-ink-2" },
  NOMINAL: { text: "text-ok", bg: "bg-ok/10", ring: "ring-ok/40", dot: "bg-ok" },
  IMAGING: { text: "text-sky", bg: "bg-sky/10", ring: "ring-sky/40", dot: "bg-sky" },
  DOWNLINK: { text: "text-violet", bg: "bg-violet/10", ring: "ring-violet/40", dot: "bg-violet" },
  SAFE: { text: "text-warn", bg: "bg-warn/10", ring: "ring-warn/40", dot: "bg-warn" },
  FAULT: { text: "text-crit", bg: "bg-crit/10", ring: "ring-crit/50", dot: "bg-crit" },
};

export const SEVERITY_STYLE: Record<Severity, string> = {
  INFO: "text-sky bg-sky/10 ring-sky/30",
  WARNING: "text-warn bg-warn/10 ring-warn/30",
  CRITICAL: "text-crit bg-crit/10 ring-crit/40",
};

export const STATUS_STYLE: Record<string, string> = {
  SENT: "text-ink-2 bg-ink-3/15 ring-ink-3/30",
  ACCEPTED: "text-sky bg-sky/10 ring-sky/30",
  COMPLETED: "text-ok bg-ok/10 ring-ok/30",
  REJECTED: "text-crit bg-crit/10 ring-crit/30",
  FAILED: "text-crit bg-crit/10 ring-crit/30",
  TIMEOUT: "text-warn bg-warn/10 ring-warn/30",
};
