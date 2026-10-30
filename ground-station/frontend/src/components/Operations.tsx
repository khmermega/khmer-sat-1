import { useEffect, useState } from "react";
import { api, ApiError, type CatalogEntry, type Status } from "../api";
import { Button, Chip, Field, inputCls, Panel } from "./Panel";

type Notify = (msg: string, tone?: "ok" | "err") => void;

function errText(e: unknown): string {
  if (e instanceof ApiError) return `${e.status}: ${e.message}`;
  return e instanceof Error ? e.message : String(e);
}

// ---------------------------------------------------------------- camera
const RESOLUTIONS = [
  [640, 480],
  [1280, 960],
  [1920, 1440],
  [2592, 1944],
] as const;

export function CameraControl({ status, role, notify }: { status: Status | null; role: string | null; notify: Notify }) {
  const [res, setRes] = useState("1280x960");
  const [quality, setQuality] = useState(85);
  const [delay, setDelay] = useState(60);
  const mode = status?.onboard?.mode;
  const soc = status?.telemetry?.power.soc_pct ?? 0;
  const faults = status?.telemetry?.faults ?? [];
  const [w, h] = res.split("x").map(Number);
  const inhibit =
    !role
      ? "Sign in to command"
      : mode && !["NOMINAL", "IMAGING"].includes(mode)
        ? `Imaging inhibited in ${mode}`
        : soc < 50
          ? "SoC below imaging threshold (50%)"
          : faults.find((f) => ["CAMERA_FAILURE", "STORAGE_FULL", "PAYLOAD_OVERTEMP", "PAYLOAD_UNDERTEMP"].includes(f));

  const run = async (type: string, args: Record<string, unknown>, label: string) => {
    try {
      await api.send(type, args);
      notify(`${label} sent`);
    } catch (e) {
      notify(errText(e), "err");
    }
  };

  return (
    <Panel
      testId="camera"
      title="Payload · Camera"
      subtitle={status?.onboard ? `default ${status.onboard.camera.width}×${status.onboard.camera.height} q${status.onboard.camera.jpeg_quality} · ${status.onboard.scheduled_captures} scheduled · ${status.onboard.downlink_queue} queued` : "—"}
      actions={<Chip className="text-gold bg-gold/10 ring-gold/30">mock · synthetic scenes</Chip>}
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="Resolution">
          <select className={inputCls} value={res} onChange={(e) => setRes(e.target.value)}>
            {RESOLUTIONS.map(([a, b]) => (
              <option key={a} value={`${a}x${b}`}>
                {a} × {b}
              </option>
            ))}
          </select>
        </Field>
        <Field label={`JPEG quality · ${quality}`}>
          <input type="range" min={10} max={95} value={quality} onChange={(e) => setQuality(Number(e.target.value))} className="mt-2 accent-[#f5b301]" />
        </Field>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="primary" disabled={!!inhibit} title={inhibit || undefined} onClick={() => run("CAPTURE_IMAGE", { width: w, height: h, jpeg_quality: quality }, "Capture")}>
          ◉ Capture now
        </Button>
        <Button disabled={!role} onClick={() => run("SET_CAMERA_CONFIG", { width: w, height: h, jpeg_quality: quality }, "Camera config")}>
          Set as default
        </Button>
        <Button disabled={!role} onClick={() => run("START_DOWNLINK", {}, "Downlink")}>
          ⇣ Start downlink
        </Button>
      </div>
      <div className="mt-3 flex items-end gap-2">
        <Field label="Time-tagged capture in (sim s)">
          <input type="number" min={5} max={86400} className={inputCls} value={delay} onChange={(e) => setDelay(Number(e.target.value))} />
        </Field>
        <Button
          disabled={!role || !status?.sim}
          onClick={() => {
            const at = new Date(new Date(status!.sim!.utc).getTime() + delay * 1000).toISOString();
            run("SCHEDULE_CAPTURE", { at_utc: at, width: w, height: h, jpeg_quality: quality }, `Capture scheduled ${at.slice(11, 19)}Z`);
          }}
        >
          Schedule
        </Button>
      </div>
      {inhibit && role && <p className="mt-2 text-[11px] text-warn">⚠ {inhibit}</p>}
      <p className="mt-2 text-[10px] leading-relaxed text-ink-3">
        Simulation uses procedurally generated scenes stamped “SIMULATED”. Real camera frames captured on the ground are tagged GROUND_TEST_HARDWARE and are never labelled orbital.
      </p>
    </Panel>
  );
}

// ---------------------------------------------------------------- commands
export function CommandConsole({ role, notify }: { role: string | null; notify: Notify }) {
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [type, setType] = useState("PING");
  const [args, setArgs] = useState("{}");
  const [arm, setArm] = useState<{ arm_id: string; type: string; expires: number } | null>(null);
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    api.catalog().then(setCatalog).catch(() => {});
  }, []);
  useEffect(() => {
    if (!arm) return;
    const t = setInterval(() => {
      const r = Math.max(0, Math.ceil((arm.expires - Date.now()) / 1000));
      setRemaining(r);
      if (r === 0) setArm(null);
    }, 250);
    return () => clearInterval(t);
  }, [arm]);

  const entry = catalog.find((c) => c.type === type);
  const presets: Record<string, string> = {
    SET_MODE: '{"mode": "SAFE"}',
    SET_TELEMETRY_RATE: '{"period_s": 2}',
    SET_CAMERA_CONFIG: '{"width": 1280, "height": 960, "jpeg_quality": 85}',
  };

  const send = async () => {
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(args || "{}");
    } catch {
      notify("Arguments must be valid JSON", "err");
      return;
    }
    try {
      if (entry?.critical) {
        const a = await api.arm(type, parsed);
        setArm({ arm_id: a.arm_id, type: a.type, expires: Date.now() + a.expires_in_s * 1000 });
        notify(`${type} ARMED — confirm within ${a.expires_in_s}s`);
      } else {
        await api.send(type, parsed);
        notify(`${type} sent`);
      }
    } catch (e) {
      notify(errText(e), "err");
    }
  };

  const execute = async () => {
    if (!arm) return;
    try {
      await api.execute(arm.arm_id);
      notify(`${arm.type} executed`);
    } catch (e) {
      notify(errText(e), "err");
    } finally {
      setArm(null);
    }
  };

  return (
    <Panel testId="commands" title="Telecommand" subtitle="HMAC-SHA256 signed · anti-replay · onboard interlocks" actions={<Chip className="text-ink-2 bg-ink-3/10 ring-line-2">{role ?? "read-only"}</Chip>}>
      <div className="grid grid-cols-1 gap-3">
        <Field label="Command">
          <select
            className={inputCls}
            value={type}
            onChange={(e) => {
              setType(e.target.value);
              setArgs(presets[e.target.value] ?? "{}");
              setArm(null);
            }}
          >
            {catalog.map((c) => (
              <option key={c.type} value={c.type}>
                {c.critical ? "⚠ " : ""}
                {c.type}
              </option>
            ))}
          </select>
        </Field>
        {entry && <p className="-mt-1 text-[11px] text-ink-3">{entry.description}</p>}
        <Field label="Arguments (JSON)">
          <textarea rows={2} className={`${inputCls} font-mono`} value={args} onChange={(e) => setArgs(e.target.value)} spellCheck={false} />
        </Field>
      </div>
      {arm ? (
        <div className="mt-3 rounded-lg border border-crit/50 bg-crit/10 p-3" data-testid="arm-confirm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-crit">⚠ {arm.type} armed</span>
            <span className="font-mono text-xs text-crit">{remaining}s</span>
          </div>
          <p className="mt-1 text-[11px] text-ink-2">Safety-critical command. Confirm to transmit, or let the arm expire.</p>
          <div className="mt-2 flex gap-2">
            <Button variant="danger" onClick={execute}>
              Confirm &amp; transmit
            </Button>
            <Button variant="ghost" onClick={() => setArm(null)}>
              Abort
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex items-center gap-2">
          <Button variant={entry?.critical ? "danger" : "primary"} disabled={!role || (entry?.critical && role !== "admin")} onClick={send}>
            {entry?.critical ? "Arm (step 1/2)" : "Send"}
          </Button>
          {entry?.critical && role !== "admin" && <span className="text-[11px] text-warn">Admin role required</span>}
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- faults
const TOGGLES: { key: string; label: string; on: unknown; off: unknown }[] = [
  { key: "camera_failure", label: "Camera failure", on: true, off: false },
  { key: "battery_drain_w", label: "Battery drain 25 W", on: 25, off: 0 },
  { key: "payload_heater_w", label: "Payload over-temp", on: 8, off: 0 },
  { key: "gnss_outage", label: "GNSS outage", on: true, off: false },
  { key: "fsw_hang", label: "Flight SW hang (watchdog)", on: true, off: false },
  { key: "link_down", label: "Network disconnect", on: true, off: false },
  { key: "storage_fill", label: "Storage exhaustion", on: true, off: false },
  { key: "db_outage", label: "Ground DB outage", on: true, off: false },
];

export function FaultInjection({ status, role, notify }: { status: Status | null; role: string | null; notify: Notify }) {
  const f = status?.faults ?? {};
  const set = async (body: Record<string, unknown>) => {
    try {
      await api.setFaults(body);
    } catch (e) {
      notify(errText(e), "err");
    }
  };
  const isOn = (k: string) => !!f[k] && f[k] !== 0;
  if (status?.gs_mode === "HARDWARE") return null;

  return (
    <Panel testId="faults" title="Fault injection" subtitle="Simulation only · exercises FDIR and ground resilience" actions={<Chip className="text-gold bg-gold/10 ring-gold/30">SIM</Chip>}>
      <div className="grid grid-cols-2 gap-2">
        {TOGGLES.map((t) => {
          const on = isOn(t.key);
          return (
            <button
              key={t.key}
              disabled={!role}
              onClick={() => set({ [t.key]: on ? t.off : t.on })}
              className={`flex items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-[11px] ring-1 ring-inset transition disabled:cursor-not-allowed disabled:opacity-40 ${
                on ? "bg-crit/15 text-crit ring-crit/50" : "bg-deck/60 text-ink-2 ring-line hover:ring-line-2"
              }`}
            >
              <span>{t.label}</span>
              <span className={`h-2 w-2 shrink-0 rounded-full ${on ? "bg-crit blink" : "bg-line-2"}`} />
            </button>
          );
        })}
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        {[
          ["packet_loss", "Loss"],
          ["packet_corrupt", "Corrupt"],
          ["packet_duplicate", "Duplicate"],
        ].map(([k, label]) => (
          <Field key={k} label={`${label} ${Math.round(Number(f[k] ?? 0) * 100)}%`}>
            <input
              type="range"
              min={0}
              max={30}
              disabled={!role}
              value={Math.round(Number(f[k] ?? 0) * 100)}
              onChange={(e) => set({ [k]: Number(e.target.value) / 100 })}
              className="accent-[#f87171]"
            />
          </Field>
        ))}
      </div>
      <div className="mt-3 flex justify-end">
        <Button
          variant="ghost"
          disabled={!role}
          onClick={() =>
            set(Object.fromEntries([...TOGGLES.map((t) => [t.key, t.off]), ["packet_loss", 0], ["packet_corrupt", 0], ["packet_duplicate", 0], ["packet_delay_s", 0]]))
          }
        >
          Clear all faults
        </Button>
      </div>
    </Panel>
  );
}
