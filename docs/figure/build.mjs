// KHMER-SAT 1 — isometric figure of the 3U CubeSat prototype (anatomy kit).
//   node docs/figure/build.mjs           -> docs/figure/khmer-sat-1-prototype.html        (light, white page)
//   node docs/figure/build.mjs --dark    -> docs/figure/khmer-sat-1-prototype-dark.html
// The body follows the 3U CubeSat envelope (100 x 100 x 340.5 mm). Wing size, cell layout,
// antennas and optics are illustrative placeholders: the real parts are TBD (docs/hardware-bom.md).
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "./kit/iso-kit.mjs";
import * as G from "./kit/lathe.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const theme = process.argv.includes("--dark") ? "dark" : "light";
const kitScript = () => readFileSync(join(HERE, "kit", "iso-kit.mjs"), "utf8").replace(/^export /gm, "");

// ---------------------------------------------------------------- world (1 unit = 3 mm)
const WIDTH = 640;
const HEIGHT = 400;
const L = 114; // 340.5 mm
const W = 34; // 100 mm
const HX = L / 2;
const HW = W / 2;
const RAIL = 3;
const PANEL = 0.8; // side panels sit this far inside the rails
const BODY = { x: -HX, y: -HW + PANEL, w: L, d: W - 2 * PANEL, r: 0.3 };
const ZB = -HW + PANEL; // body panel bottom
const ZT = HW - PANEL; // body panel top
const YF = HW - PANEL; // +y face
const XF = HX; // +x end face (camera)
const UNITS = [-HX, -HX + 38, -HX + 76, HX];

const WING = { gap: 2, depth: 32, between: 1.6, len: 102, t: 1.2, z: -HW };
const SHADOW_Z = -46;

const P = k.fitProjection(
  [
    [-HX - 2, -HW - 2 * WING.depth - 6, WING.z],
    [HX + 2, HW + 2 * WING.depth + 6, WING.z],
    [-HX, -HW - 30, HW + 2],
    [-HX, HW + 30, HW + 2],
    [XF + 12, 0, 0],
    ...k.boxCorners({ x: -HX, y: -HW - 66, w: L, d: W + 132, r: 0 }, SHADOW_Z, SHADOW_Z),
  ],
  WIDTH,
  HEIGHT,
  { pad: 22, azimuth: 40 },
);

const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const Ln = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const path = (points) => `M${points.map((p) => at(p).map((v) => v.toFixed(1)).join(" ")).join("L")}Z`;
const poly = (points, cls) => `<path class="${cls}" d="${path(points)}"/>`;

// ---------------------------------------------------------------- parts
const railPlan = (y) => ({ x: -HX - 1.5, y, w: L + 3, d: RAIL, r: 0.4 });
const rail = (y, z) => S(k.slabOf(railPlan(y), z, RAIL, P, 2, 0.3), { tone: "hi", crease: "lo", className: "c-alu" });

// A solar cell in a plane: corners clipped, two bus bars, fingers that end on its outline.
function cell(pt, u0, u1, v0, v1, fingersAlong = "u") {
  const c = Math.min(1.4, (u1 - u0) / 6);
  const out = [poly([pt(u0 + c, v0), pt(u1 - c, v0), pt(u1, v0 + c), pt(u1, v1 - c), pt(u1 - c, v1), pt(u0 + c, v1), pt(u0, v1 - c), pt(u0, v0 + c)], "cell")];
  const lines = [];
  if (fingersAlong === "u") for (let v = v0 + 2.2; v < v1 - 1.2; v += 2.2) lines.push(k.segment(pt(u0, v), pt(u1, v), P));
  else for (let u = u0 + 2.2; u < u1 - 1.2; u += 2.2) lines.push(k.segment(pt(u, v0), pt(u, v1), P));
  out.push(`<path class="cell-finger" d="${lines.join("")}"/>`);
  const bus = fingersAlong === "u" ? [u0 + (u1 - u0) / 3, u0 + (2 * (u1 - u0)) / 3].map((u) => k.segment(pt(u, v0), pt(u, v1), P)) : [v0 + (v1 - v0) / 3, v0 + (2 * (v1 - v0)) / 3].map((v) => k.segment(pt(u0, v), pt(u1, v), P));
  out.push(`<path class="cell-bus" d="${bus.join("")}"/>`);
  return out.join("");
}

function sideCells() {
  // +y face: two cells per unit
  const pt = (u, v) => [u, YF + 0.05, v];
  const out = [];
  for (let i = 0; i < 3; i++) {
    const a = UNITS[i] + 1.6, b = UNITS[i + 1] - 1.6, mid = (a + b) / 2;
    out.push(cell(pt, a, mid - 0.6, ZB + RAIL, ZT - RAIL), cell(pt, mid + 0.6, b, ZB + RAIL, ZT - RAIL));
  }
  // panel joints between the units, edge to edge
  out.push(Ln(UNITS.slice(1, 3).map((x) => k.segment([x, YF + 0.05, ZB], [x, YF + 0.05, ZT], P) + k.segment([x, -YF, ZT + 0.05], [x, YF, ZT + 0.05], P)).join(""), { tone: "lo" }));
  return out.join("");
}

function topDeck() {
  const z = ZT + 0.05;
  const pt = (u, v) => [u, v, z];
  const out = [];
  // units 2 and 3: two cells each
  for (let i = 1; i < 3; i++) {
    const a = UNITS[i] + 1.6, b = UNITS[i + 1] - 1.6;
    out.push(cell(pt, a, b, -YF + RAIL, -0.6, "v"), cell(pt, a, b, 0.6, YF - RAIL, "v"));
  }
  // unit 1: UHF antenna module with GPS patch and sun sensor
  const ant = { x: -HX + 3, y: -YF + 2.4, w: 32, d: 2 * YF - 4.8, r: 0.8 };
  out.push(S(k.slabOf(ant, ZT, 2.6, P, 3, 0.4), { tone: "mid", className: "c-dark" }));
  out.push(Ln(k.planOutline(k.insetPlan(ant, 1.6), ZT + 2.6, P, 3), { tone: "lo" }));
  const gps = { x: ant.x + 5, y: -6, w: 12, d: 12, r: 0.6 };
  out.push(S(k.slabOf(gps, ZT + 2.6, 1.2, P, 2, 0.3), { tone: "hi", className: "c-ceramic" }));
  out.push(Ln(k.planOutline(k.insetPlan(gps, 3), ZT + 3.8, P, 2), { tone: "lo" }));
  out.push(D([at([gps.x + 8.5, gps.y + 6, ZT + 3.8])], { size: 0.6, tone: "hi" }));
  const sun = { x: ant.x + 22, y: -3, w: 6, d: 6, r: 0.5 };
  out.push(S(k.slabOf(sun, ZT + 2.6, 1, P, 2, 0.2), { tone: "lo", className: "c-dark" }));
  out.push(Ln(k.planOutline({ x: sun.x + 2.6, y: sun.y + 1.2, w: 0.8, d: 3.6, r: 0.3 }, ZT + 3.6, P, 2), { tone: "hi" }));
  out.push(D(k.corners(ant, 1.2).map(([x, y]) => at([x, y, ZT + 2.6])), { size: 0.35 }));
  return out.join("");
}

// Four deployed tape-spring UHF antennas from the module, along ±y.
const WHISKERS = [-HX + 9, -HX + 29].flatMap((x) => [
  [[x, -YF + 2.4, ZT + 1.6], [x, -HW - 34, ZT + 1.6]],
  [[x, YF - 2.4, ZT + 1.6], [x, HW + 34, ZT + 1.6]],
]);
const whiskers = (side) =>
  WHISKERS.filter(([, b]) => Math.sign(b[1]) === side)
    .map(([a, b]) => `<g class="antenna">${k.wireSvg(at(a), at(b), { tone: "hi", size: 0.7 })}</g>`)
    .join("");

// Turned camera lens on the +x end face.
const F = G.frameAlong([XF, 0, 0], [1, 0, 0]);
function lens() {
  const out = [];
  out.push(S(G.disc(0, 1.4, 11.5, F, P), { tone: "mid", className: "c-gold" }));
  out.push(D(G.dotsOf(F, 1.4, 10, 6, P, { all: true, phase: 0.3 }), { size: 0.45, tone: "hi" }));
  out.push(S(G.disc(1.4, 9, 8.4, F, P), { tone: "mid", className: "c-dark", inner: k.fadedSvg(G.ribsOf(F, 2.4, 8, 8.4, 44, P, { fade: [0.1, 0.5], seams: true }), { tone: "lo" }) }));
  out.push(S(G.disc(9, 10, 9, F, P), { tone: "mid", className: "c-gold" }));
  out.push(`<g data-part="glass">${S(G.disc(10, 10.3, 6.4, F, P), { tone: "hi", className: "c-glass", crease: "none" })}</g>`);
  out.push(`<g data-part="glint">${Ln(G.circleOf(F, 10.3, 4.6, P), { tone: "hi", className: "glint" })}${Ln(G.circleOf(F, 10.3, 2, P), { tone: "hi", className: "glint" })}</g>`);
  return out.join("");
}

// End-face details: corner screws, remove-before-flight pin and tag, heartbeat LED.
function endFace() {
  const out = [];
  const pt = (y, z) => [XF + 0.05, y, z];
  out.push(D([pt(-YF + 4, ZB + 4), pt(YF - 4, ZB + 4), pt(-YF + 4, ZT - 4), pt(YF - 4, ZT - 4)].map(at), { size: 0.45, tone: "mid" }));
  const y = YF - 5, z = ZB + 9;
  out.push(S(k.slabOf({ x: XF, y: y - 1.2, w: 2.6, d: 2.4, r: 0.4 }, z - 1.2, 2.4, P, 2), { tone: "mid", className: "c-red" }));
  out.push(poly([[XF + 2.8, y - 2.4, z - 1], [XF + 2.8, y + 2.4, z - 1], [XF + 2.8, y + 3.2, z - 15], [XF + 2.8, y - 3.2, z - 15]], "rbf-tag"));
  out.push(Ln(k.segment([XF + 2.8, y - 2.9, z - 11], [XF + 2.8, y + 2.9, z - 11], P), { tone: "hi", className: "rbf-line" }));
  const ledAt = at(pt(-YF + 5, ZT - 9));
  out.push(`<circle data-part="led" class="ks-green" cx="${ledAt[0].toFixed(1)}" cy="${ledAt[1].toFixed(1)}" r="0.8" opacity=".3"/>`);
  return out.join("");
}

// A deployed wing: two full-length panels hinged on the body's lower long edge.
function wing(side) {
  const out = [];
  const z = WING.z;
  for (let p = 0; p < 2; p++) {
    const y0 = side > 0 ? HW + WING.gap + p * (WING.depth + WING.between) : -HW - WING.gap - (p + 1) * WING.depth - p * WING.between;
    const plan = { x: -WING.len / 2, y: y0, w: WING.len, d: WING.depth, r: 0.6 };
    out.push(S(k.slabOf(plan, z, WING.t, P, 2, 0.3), { tone: "mid", crease: "lo", className: "c-panel" }));
    const top = z + WING.t;
    const pt = (u, v) => [u, v, top];
    const cw = (WING.len - 2.4 - 5 * 1.2) / 6;
    const cd = (WING.depth - 2.4 - 1.2) / 2;
    for (let i = 0; i < 6; i++) {
      for (let j = 0; j < 2; j++) {
        const u0 = plan.x + 1.2 + i * (cw + 1.2), v0 = plan.y + 1.2 + j * (cd + 1.2);
        out.push(cell(pt, u0, u0 + cw, v0, v0 + cd, "v"));
      }
    }
  }
  // gold hinge knuckles: body to first panel, and between the two panels
  const hinges = side > 0 ? [HW - 0.6, HW + WING.gap + WING.depth - 0.4] : [-HW - WING.gap - 1.4, -HW - WING.gap - WING.depth - WING.between - 0.2];
  for (const hy of hinges) for (const x of [-38, 0, 38]) out.push(S(k.slabOf({ x: x - 3, y: hy, w: 6, d: 2, r: 0.5 }, z - 0.3, WING.t + 0.8, P, 2, 0.2), { tone: "mid", className: "c-gold" }));
  return out.join("");
}

// ---------------------------------------------------------------- colour
const COLOURS = {
  light: { panel: "#1f2f52", alu: "#c9ced6", gold: "#d39a24", dark: "#30353d", glass: "#0f2a4a", red: "#d63c2f", ceramic: "#efe7d6",
    cell: "#2a5bd7", cellEdge: "#173079", finger: "rgba(220,232,255,.42)", bus: "rgba(238,243,255,.85)", antenna: "#59606b", green: "#16a34a", glint: "#5fd4ff", tagLine: "#ffe4e0" },
  dark: { panel: "#1d2b47", alu: "#a7b0bd", gold: "#d6a43c", dark: "#2b2f36", glass: "#0d2440", red: "#dc4a3d", ceramic: "#d8cfbd",
    cell: "#2c5fd8", cellEdge: "#9db8ff", finger: "rgba(200,215,255,.32)", bus: "rgba(225,232,250,.7)", antenna: "#e5e7eb", green: "#34d399", glint: "#7fe0ff", tagLine: "#ffd2cc" },
}[theme];
const C = COLOURS;
const tint = (name, c) =>
  `.${name}>.iso-fill,.${name}>.iso-top{fill:${c}}` + [88, 74, 60, 48].map((m, i) => `.${name}>.iso-shade[data-shade="${i}"]{fill:color-mix(in srgb,${c} ${m}%,#000)}`).join("");
const PALETTE =
  ["panel", "alu", "gold", "dark", "glass", "red", "ceramic"].map((n) => tint("c-" + n, C[n])).join("") +
  `.cell{fill:${C.cell};stroke:${C.cellEdge};stroke-width:.3}.cell-finger{stroke:${C.finger};stroke-width:.22;fill:none}.cell-bus{stroke:${C.bus};stroke-width:.4;fill:none}` +
  `.rbf-tag{fill:${C.red};stroke:${C.tagLine};stroke-width:.3}.iso-line.rbf-line{stroke:${C.tagLine}}.iso-line.glint{stroke:${C.glint};stroke-width:.9}` +
  `.antenna .iso-line{stroke:${C.antenna};stroke-width:.7}.antenna .iso-wire-end{fill:${C.antenna}}.ks-green{fill:${C.green};stroke:none}` +
  `.c-glass>.iso-top,.c-glass>.iso-shade{fill:${C.glass}}.antenna.on .iso-line{stroke:${C.gold};stroke-width:.9}.antenna.on .iso-wire-end{fill:${C.gold}}` +
  `.sat-shadow{fill:#0b1320;opacity:${theme === "light" ? 0.16 : 0.5};filter:blur(9px)}`;

// ---------------------------------------------------------------- figure (back to front)
const shadowPlan = { x: -HX + 14, y: -HW - 2 * WING.depth + 10, w: L - 28, d: W + 4 * WING.depth - 20, r: 22 };
const svg = k.figureSvg({
  width: WIDTH,
  height: HEIGHT,
  label:
    "KHMER-SAT 1, a 3U Earth-observation CubeSat, shown as an isometric model. The 10 by 10 by 34 centimetre body has aluminium rails on its four long edges and solar cells on its faces. Two solar wings, each made of two full-length panels, are deployed from the body's lower edges on gold hinges. On top sit a UHF antenna module with four tape antennas, a GPS patch and a sun sensor; on the end face, the camera lens with a gold mount and a red remove-before-flight tag.",
  body: [
    `<style>${PALETTE}</style>`,
    `<path class="sat-shadow" d="${k.planOutline(shadowPlan, SHADOW_Z, P, 8)}"/>`,
    wing(-1),
    whiskers(-1),
    rail(-HW, -HW),
    S(k.slabOf(BODY, ZB, ZT - ZB, P, 2), { tone: "mid", crease: "lo", className: "c-panel" }),
    sideCells(),
    topDeck(),
    rail(-HW, HW - RAIL),
    endFace(),
    rail(HW - RAIL, HW - RAIL),
    rail(HW - RAIL, -HW),
    lens(),
    whiskers(1),
    wing(1),
  ],
});

// ---------------------------------------------------------------- live: the real mode cycle
const live = `
const stage = document.querySelector(".iso-stage");
const svg = stage.querySelector("svg");
const glint = svg.querySelector('[data-part="glint"]');
const led = svg.querySelector('[data-part="led"]');
const antennas = [...svg.querySelectorAll(".antenna")];
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");
// Modes and the imaging hold are the flight software's own (onboard/safety/modes.py, onboard/config.py).
const STEPS = [
  { mode: "NOMINAL", text: "NOMINAL · solar wings charging", secs: 4 },
  { mode: "IMAGING", text: "IMAGING · 5 s capture hold", secs: 5 },
  { mode: "DOWNLINK", text: "DOWNLINK · image chunks to ground", secs: 4 },
  { mode: "SAFE", text: "SAFE · minimum load, waiting for ground", secs: 3 },
];
let step = 0, t = 0, frame = 0, last = 0, visible = false, clock = 0, auto = true, timer = 0;
function show() {
  const s = STEPS[step];
  if (readout.textContent !== s.text) readout.textContent = s.text;
  stage.setAttribute("aria-valuetext", s.text);
  antennas.forEach((a) => a.classList.toggle("on", s.mode === "DOWNLINK"));
}
function tick(now) {
  const dt = last ? Math.min((now - last) / 1000, 0.05) : 1 / 60;
  last = now; clock += dt;
  if (auto) { t += dt; if (t > STEPS[step].secs) { t = 0; step = (step + 1) % STEPS.length; } }
  const imaging = STEPS[step].mode === "IMAGING";
  glint.style.opacity = imaging ? String(0.7 + 0.3 * Math.sin(clock * 6)) : "0.35";
  led.setAttribute("opacity", (0.25 + 0.75 * Math.exp(-(clock % 1) * 7)).toFixed(2)); // 1 s watchdog heartbeat
  show();
  frame = visible && !still.matches ? requestAnimationFrame(tick) : 0;
}
const run = () => { if (!frame && visible && !still.matches) { last = 0; frame = requestAnimationFrame(tick); } };
const next = () => { step = (step + 1) % STEPS.length; t = 0; auto = false; clearTimeout(timer); timer = setTimeout(() => { auto = true; }, 8000); show(); run(); };
new IntersectionObserver((e) => { visible = e[e.length - 1].isIntersecting; if (visible) run(); }, { rootMargin: "120px 0px" }).observe(stage);
stage.addEventListener("click", next);
stage.addEventListener("keydown", (ev) => { if (["Enter", " ", "ArrowRight"].includes(ev.key)) { ev.preventDefault(); next(); } });
show();
`;

const body = k.plateHtml({
  fig: "Fig 1",
  title: "KHMER-SAT 1 · 3U EO CubeSat",
  hint: "Click to step through the modes",
  readout: "NOMINAL · solar wings charging",
  keys: [
    { mark: "blue", label: "Solar cells on the body and on two deployed two-panel wings" },
    { mark: "lit", label: "Camera lens on the end face; UHF antennas light during DOWNLINK" },
    { mark: "red", label: "Remove-before-flight tag (ground hardware, pulled before launch)" },
  ],
  caption:
    "The 3U body follows the CubeSat envelope, 100 × 100 × 340.5 mm. Wing size, cell layout, antennas and optics are illustrative: the real parts are still to be selected (see docs/hardware-bom.md). The modes and the 5 s imaging hold are the flight software's own; the green LED on the end face blinks with the 1 s watchdog heartbeat.",
  body: `<div class="iso-stage" tabindex="0" role="button" aria-label="KHMER-SAT 1 CubeSat model: Enter steps through the operating modes">${svg}</div>`,
});

const name = theme === "dark" ? "khmer-sat-1-prototype-dark.html" : "khmer-sat-1-prototype.html";
writeFileSync(join(HERE, name), k.pageHtml({ title: "KHMER-SAT 1 · 3U EO CubeSat", theme, body, script: kitScript() + live, width: 720 }));
console.log("wrote", name);
