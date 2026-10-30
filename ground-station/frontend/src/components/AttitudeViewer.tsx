import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { Housekeeping } from "../api";
import { fmt } from "../format";
import { Panel } from "./Panel";

/** Canvas texture that looks like a string of solar cells. */
function cellTexture(cols: number, rows: number): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 128 * cols;
  c.height = 128 * rows;
  const g = c.getContext("2d")!;
  g.fillStyle = "#0b1220";
  g.fillRect(0, 0, c.width, c.height);
  for (let i = 0; i < cols; i++) {
    for (let j = 0; j < rows; j++) {
      const x = i * 128 + 8;
      const y = j * 128 + 8;
      const grad = g.createLinearGradient(x, y, x + 112, y + 112);
      grad.addColorStop(0, "#1e3a8a");
      grad.addColorStop(1, "#0c1d4a");
      g.fillStyle = grad;
      g.fillRect(x, y, 112, 112);
      g.strokeStyle = "rgba(148,163,184,0.35)";
      g.lineWidth = 2;
      for (let k = 1; k < 4; k++) {
        g.beginPath();
        g.moveTo(x, y + k * 28);
        g.lineTo(x + 112, y + k * 28);
        g.stroke();
      }
    }
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function buildCubeSat(): THREE.Group {
  const g = new THREE.Group();
  // 3U body: 1 x 1 x 3 units with +Z (camera end) as the long axis, matching the
  // simulator's body frame (FACE_NORMALS in simulator/power/eps.py).
  const side = new THREE.MeshStandardMaterial({ map: cellTexture(1, 3), metalness: 0.3, roughness: 0.45 });
  const end = new THREE.MeshStandardMaterial({ color: 0x8a94a6, metalness: 0.8, roughness: 0.35 });
  const body = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 3), [side, side, side, side, end, end]);
  g.add(body);
  // aluminium rails
  const railMat = new THREE.MeshStandardMaterial({ color: 0xc0c7d4, metalness: 0.9, roughness: 0.25 });
  for (const [x, y] of [[0.5, 0.5], [-0.5, 0.5], [0.5, -0.5], [-0.5, -0.5]]) {
    const rail = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.09, 3.1), railMat);
    rail.position.set(x, y, 0);
    g.add(rail);
  }
  // camera lens on +Z face (nadir boresight in ideal pointing)
  const lens = new THREE.Mesh(
    new THREE.CylinderGeometry(0.28, 0.32, 0.25, 32),
    new THREE.MeshStandardMaterial({ color: 0x111827, metalness: 0.6, roughness: 0.2 }),
  );
  lens.rotation.x = Math.PI / 2;
  lens.position.z = 1.62;
  g.add(lens);
  const glass = new THREE.Mesh(new THREE.CircleGeometry(0.2, 32), new THREE.MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x0c4a6e, metalness: 1, roughness: 0 }));
  glass.position.z = 1.751;
  g.add(glass);
  // UHF antenna whiskers on -Z
  const antMat = new THREE.MeshStandardMaterial({ color: 0xe5e7eb, metalness: 0.7, roughness: 0.3 });
  for (let i = 0; i < 4; i++) {
    const a = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 1.4, 6), antMat);
    const ang = (i * Math.PI) / 2;
    a.position.set(Math.cos(ang) * 0.75, Math.sin(ang) * 0.75, -1.5);
    a.rotation.z = ang + Math.PI / 2;
    g.add(a);
  }
  // body axes
  const axes = [
    [new THREE.Vector3(1, 0, 0), 0xf87171],
    [new THREE.Vector3(0, 1, 0), 0x34d399],
    [new THREE.Vector3(0, 0, 1), 0x38bdf8],
  ] as const;
  for (const [dir, color] of axes) {
    g.add(new THREE.ArrowHelper(dir, new THREE.Vector3(0, 0, 0), dir.z ? 2.6 : 1.4, color, 0.18, 0.1));
  }
  return g;
}

export function AttitudeViewer({ hk }: { hk: Housekeeping | null | undefined }) {
  const mount = useRef<HTMLDivElement>(null);
  const target = useRef(new THREE.Quaternion());

  useEffect(() => {
    if (hk?.attitude.q) {
      const [w, x, y, z] = hk.attitude.q;
      target.current.set(x, y, z, w).normalize();
    }
  }, [hk?.attitude.q]);

  useEffect(() => {
    const el = mount.current;
    if (!el) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      el.innerHTML = '<p class="p-4 text-xs text-ink-3">WebGL unavailable - 3D attitude view disabled.</p>';
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(4.4, 3.0, 4.4);
    camera.lookAt(0, 0, 0);
    scene.add(new THREE.AmbientLight(0x8899bb, 0.6));
    const sun = new THREE.DirectionalLight(0xfff1d6, 2.4);
    sun.position.set(5, 8, 4);
    scene.add(sun);
    const rim = new THREE.DirectionalLight(0x38bdf8, 0.7);
    rim.position.set(-6, -2, -5);
    scene.add(rim);

    // Reference (simulated ECI) frame, faint
    const ref = new THREE.Group();
    const grid = new THREE.GridHelper(8, 16, 0x1e2a42, 0x13203a);
    grid.position.y = -2.4;
    ref.add(grid);
    for (const [dir, color] of [[new THREE.Vector3(1, 0, 0), 0x7f1d1d], [new THREE.Vector3(0, 1, 0), 0x065f46], [new THREE.Vector3(0, 0, 1), 0x0c4a6e]] as const) {
      ref.add(new THREE.ArrowHelper(dir, new THREE.Vector3(0, 0, 0), 3.4, color, 0.15, 0.08));
    }
    scene.add(ref);

    // starfield
    const starGeo = new THREE.BufferGeometry();
    const pos = new Float32Array(600 * 3);
    for (let i = 0; i < pos.length; i++) pos[i] = (Math.random() - 0.5) * 60;
    starGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0x9aabc6, size: 0.06 })));

    const sat = buildCubeSat();
    scene.add(sat);

    const resize = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / Math.max(1, h);
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    let raf = 0;
    const tick = () => {
      // Smoothly approach the latest telemetry attitude (display interpolation only).
      sat.quaternion.slerp(target.current, 0.12);
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.dispose();
      el.removeChild(renderer.domElement);
    };
  }, []);

  const q = hk?.attitude.q;
  const r = hk?.attitude.rate_dps;
  const rateMag = r ? Math.hypot(r[0], r[1], r[2]) : null;
  return (
    <Panel
      testId="attitude"
      title="Attitude · 3D"
      subtitle="Bench visualisation of simulated attitude — kinematic model, no control law"
      bodyClassName="p-0 flex flex-col"
    >
      <div ref={mount} className="relative h-64 w-full min-h-[16rem] flex-1 [&>canvas]:h-full [&>canvas]:w-full" />
      <div className="grid grid-cols-2 gap-px border-t border-line bg-line font-mono text-[11px] tabular">
        <div className="bg-panel px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-ink-3">Quaternion [w x y z]</div>
          <div className="mt-0.5 text-ink">{q ? q.map((v) => v.toFixed(3)).join("  ") : "—"}</div>
        </div>
        <div className="bg-panel px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-ink-3">Body rate (IMU)</div>
          <div className="mt-0.5 text-ink">{r ? `${r.map((v) => v.toFixed(2)).join(" ")} °/s` : "—"}</div>
        </div>
        <div className="bg-panel px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-ink-3">|ω|</div>
          <div className="mt-0.5 text-ink">{fmt(rateMag, 3, " °/s")}</div>
        </div>
        <div className="bg-panel px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-ink-3">Magnetometer</div>
          <div className="mt-0.5 text-ink">{hk ? `${hk.attitude.mag_ut.map((v) => v.toFixed(1)).join(" ")} µT` : "—"}</div>
        </div>
      </div>
    </Panel>
  );
}
