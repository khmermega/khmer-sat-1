import { useCallback, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";
import { AttitudeViewer } from "./components/AttitudeViewer";
import { GroundTrackMap } from "./components/GroundTrackMap";
import { KpiTiles } from "./components/KpiTiles";
import { LinkPanel } from "./components/LinkPanel";
import { LoginDialog } from "./components/LoginDialog";
import { CameraControl, CommandConsole, FaultInjection } from "./components/Operations";
import { CommandHistory, EventsPanel, ImageGallery } from "./components/Records";
import { TelemetryCharts } from "./components/TelemetryCharts";
import { TopBar } from "./components/TopBar";
import { useMission } from "./useMission";

interface Toast {
  id: number;
  msg: string;
  tone: "ok" | "err";
}

export default function App() {
  const m = useMission();
  const [role, setRole] = useState<string | null>(null);
  const [login, setLogin] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    if (getToken()) api.whoami().then((w) => setRole(w.role)).catch(() => setToken(""));
  }, []);

  const notify = useCallback((msg: string, tone: "ok" | "err" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, msg, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);

  const sim = async (body: { time_scale?: number; link_mode?: string }) => {
    try {
      await api.simControl(body);
    } catch (e) {
      notify(e instanceof Error ? e.message : String(e), "err");
    }
  };

  const hk = m.status?.telemetry;
  const hardware = m.status?.gs_mode === "HARDWARE";

  return (
    <div className="min-h-full">
      <TopBar
        status={m.status}
        ws={m.ws}
        role={role}
        onLogin={() => setLogin(true)}
        onLogout={() => {
          setToken("");
          setRole(null);
        }}
        onTimeScale={(s) => sim({ time_scale: s })}
      />

      {!hardware && (
        <div className="border-b border-gold/20 bg-gold/[0.06] px-4 py-1.5 text-center text-[11px] text-gold/90">
          SIMULATION — synthetic orbit ({m.trackLabel || "not real tracking data"}), simulated telemetry and procedurally generated imagery. Nothing on this screen is
          real spacecraft data.
        </div>
      )}
      {hardware && (
        <div className="border-b border-crit/30 bg-crit/10 px-4 py-1.5 text-center text-[11px] text-crit">
          HARDWARE mode — no onboard link configured yet. Bench integration is the next milestone (M3).
        </div>
      )}

      <main className="mx-auto max-w-[1800px] space-y-4 px-4 py-4 lg:px-6">
        <KpiTiles hk={hk} status={m.status} />

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
          <div className="xl:col-span-8">
            <GroundTrackMap status={m.status} track={m.track} label={m.trackLabel} />
          </div>
          <div className="xl:col-span-4">
            <AttitudeViewer hk={hk} />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
          <div className="xl:col-span-8">
            <TelemetryCharts history={m.history} />
          </div>
          <div className="xl:col-span-4">
            <LinkPanel status={m.status} passes={m.passes} role={role} onLinkMode={(l) => sim({ link_mode: l })} />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <CameraControl status={m.status} role={role} notify={notify} />
          <CommandConsole role={role} notify={notify} />
          <FaultInjection status={m.status} role={role} notify={notify} />
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
          <div className="xl:col-span-7">
            <ImageGallery images={m.images} />
          </div>
          <div className="xl:col-span-5">
            <EventsPanel events={m.events} role={role} onAck={m.refreshEvents} />
          </div>
        </div>

        <CommandHistory commands={m.commands} />

        <footer className="flex flex-wrap items-center justify-between gap-2 pb-6 pt-2 text-[10px] text-ink-3">
          <span>
            KHMER-SAT 1 engineering prototype · protocol v{m.status?.satellite?.protocol_version ?? 1} · sat id 0x{(m.status?.satellite?.id ?? 0x4b31).toString(16).toUpperCase()}
          </span>
          <span>Not flight qualified. No RF transmission without authorization.</span>
        </footer>
      </main>

      {login && (
        <LoginDialog
          onClose={() => setLogin(false)}
          onSuccess={(r) => {
            setRole(r);
            setLogin(false);
            notify(`Signed in as ${r}`);
          }}
        />
      )}

      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`rounded-lg px-3 py-2 text-xs shadow-xl ring-1 backdrop-blur ${t.tone === "ok" ? "bg-panel-2/95 text-ink ring-line-2" : "bg-crit/15 text-crit ring-crit/50"}`}
          >
            {t.msg}
          </div>
        ))}
      </div>
    </div>
  );
}
