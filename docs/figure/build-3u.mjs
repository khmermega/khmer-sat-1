// KHMER-SAT 1 — the 3U CubeSat design, drawn in the style of the concept illustration (anatomy kit).
//   node docs/figure/build-3u.mjs           -> docs/figure/khmer-sat-1-3u.html        (light, white page)
//   node docs/figure/build-3u.mjs --dark    -> docs/figure/khmer-sat-1-3u-dark.html
// The body is the 3U envelope (100 x 100 x 340.5 mm). Wing size, cells, antennas and optics
// are illustrative placeholders: the real parts are TBD (docs/hardware-bom.md).
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
const HEIGHT = 420;
const L = 114; // 340.5 mm
const HX = L / 2;
const HW = 17; // 100 mm / 2
const RAIL = 3;
const IN = 0.8; // panels sit inside the rails
const ZB = -HW + IN, ZT = HW - IN, YF = HW - IN, XF = HX;
const UNITS = [-HX, -HX + 38, -HX + 76, HX];
const WING = { len: 102, depth: 32, gap: 1.6, between: 1.4, t: 0.9, tilt: (8 * Math.PI) / 180 };

// Point on a wing: u along x, v outward from the hinge line, n along the panel normal.
function wingPoint(side, u, v, n) {
  const c = Math.cos(WING.tilt), s = Math.sin(WING.tilt);
  return [u, side * (HW + WING.gap + c * v) - side * s * n, -HW + s * v + c * n];
}
const SPAN = 2 * WING.depth + WING.between;

const P = k.fitProjection(
  [
    ...[-1, 1].flatMap((side) => [-WING.len / 2, WING.len / 2].flatMap((u) => [0, SPAN].map((v) => wingPoint(side, u, v, 0)))),
    [-HX, -HW - 30, HW + 3], [-HX, HW + 30, HW + 3], [XF + 12, 0, 0], [-HX - 3, 0, HW], [HX, HW, -HW - 4],
  ],
  WIDTH,
  HEIGHT,
  { pad: 24, azimuth: 38, elevation: 26 },
);

const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const Ln = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const poly = (points, cls) => `<path class="${cls}" d="M${points.map((p) => at(p).map((v) => v.toFixed(1)).join(" ")).join("L")}Z"/>`;
const X = [1, 0, 0];

// ---------------------------------------------------------------- body
const rail = (y, z) => S(k.slabOf({ x: -HX - 1.5, y, w: L + 3, d: RAIL, r: 0.4 }, z, RAIL, P, 2, 0.3), { tone: "hi", crease: "lo", className: "c-silver" });

// Rail-end deployment switches (spring plungers) on the +x end of each visible rail.
function plungers() {
  return [[HW - 1.5, HW - 1.5], [HW - 1.5, -HW + 1.5], [-HW + 1.5, HW - 1.5]]
    .map(([y, z]) => S(G.disc(0, 2.2, 0.9, G.frameAlong([HX + 1.5, y, z], X), P), { tone: "mid", className: "c-gold" }))
    .join("");
}

// A light-blue cell field on a face: one fill and a white grid whose lines run edge to edge.
function cellField(pt, u0, u1, v0, v1, cols, rows) {
  const out = [poly([pt(u0, v0), pt(u1, v0), pt(u1, v1), pt(u0, v1)], "cells")];
  const grid = [], fine = [];
  for (let i = 1; i < cols; i++) grid.push(k.segment(pt(u0 + ((u1 - u0) * i) / cols, v0), pt(u0 + ((u1 - u0) * i) / cols, v1), P));
  for (let j = 1; j < rows; j++) grid.push(k.segment(pt(u0, v0 + ((v1 - v0) * j) / rows), pt(u1, v0 + ((v1 - v0) * j) / rows), P));
  for (let i = 0; i < cols * 3; i++) if (i % 3) fine.push(k.segment(pt(u0 + ((u1 - u0) * i) / (cols * 3), v0), pt(u0 + ((u1 - u0) * i) / (cols * 3), v1), P));
  out.push(`<path class="cell-fine" d="${fine.join("")}"/>`, `<path class="cell-grid" d="${grid.join("")}"/>`);
  out.push(poly([pt(u0, v0), pt(u1, v0), pt(u1, v1), pt(u0, v1)], "cell-rim"));
  return out.join("");
}

function faces() {
  const out = [S(k.slabOf({ x: -HX, y: -YF, w: L, d: 2 * YF, r: 0.3 }, ZB, ZT - ZB, P, 2), { tone: "mid", crease: "lo", className: "c-gun" })];
  // +y face: one cell field per unit, gold MLI strip at each unit joint
  const side = (u, v) => [u, YF + 0.05, v];
  for (let i = 0; i < 3; i++) out.push(cellField(side, UNITS[i] + 2, UNITS[i + 1] - 2, ZB + RAIL + 0.6, ZT - RAIL - 0.6, 4, 2));
  // top: units 2 and 3 carry cells
  const top = (u, v) => [u, v, ZT + 0.05];
  for (let i = 1; i < 3; i++) out.push(cellField(top, UNITS[i] + 2, UNITS[i + 1] - 2, -YF + RAIL + 0.6, YF - RAIL - 0.6, 4, 2));
  for (const x of UNITS.slice(1, 3)) {
    out.push(poly([[x - 1.1, YF + 0.06, ZB], [x + 1.1, YF + 0.06, ZB], [x + 1.1, YF + 0.06, ZT], [x - 1.1, YF + 0.06, ZT]], "mli"));
    out.push(poly([[x - 1.1, -YF, ZT + 0.06], [x + 1.1, -YF, ZT + 0.06], [x + 1.1, YF, ZT + 0.06], [x - 1.1, YF, ZT + 0.06]], "mli"));
  }
  return out.join("");
}

// Unit 1 top deck: UHF antenna module, GPS patch, sun sensor and a small star tracker.
function deck() {
  const out = [];
  const ant = { x: -HX + 2.5, y: -YF + 2.6, w: 33, d: 2 * YF - 5.2, r: 0.8 };
  out.push(S(k.slabOf(ant, ZT, 2.4, P, 3, 0.4), { tone: "mid", className: "c-copper" }));
  out.push(Ln(k.planOutline(k.insetPlan(ant, 1.6), ZT + 2.4, P, 3), { tone: "lo" }));
  const gps = { x: ant.x + 4, y: -6.5, w: 12, d: 12, r: 0.6 };
  out.push(S(k.slabOf(gps, ZT + 2.4, 1.2, P, 2, 0.3), { tone: "hi", className: "c-ceramic" }));
  out.push(Ln(k.planOutline(k.insetPlan(gps, 3), ZT + 3.6, P, 2), { tone: "lo" }));
  out.push(D([at([gps.x + 8.4, gps.y + 6, ZT + 3.6])], { size: 0.6, tone: "hi" }));
  const sun = { x: ant.x + 20, y: -9, w: 5, d: 5, r: 0.5 };
  out.push(S(k.slabOf(sun, ZT + 2.4, 0.9, P, 2, 0.2), { tone: "lo", className: "c-gun" }));
  out.push(Ln(k.planOutline({ x: sun.x + 2.1, y: sun.y + 1, w: 0.8, d: 3, r: 0.3 }, ZT + 3.3, P, 2), { tone: "hi" }));
  const st = [ant.x + 26, 4.5];
  out.push(S(k.cylinder(st[0], st[1], 3.2, ZT + 2.4, 2.4, P, 28), { tone: "mid", className: "c-gun" }));
  out.push(S(k.cylinder(st[0], st[1], 2.4, ZT + 4.8, 2.6, P, 28, 0.3), { tone: "mid", className: "c-gold" }));
  out.push(S(k.cylinder(st[0], st[1], 1.4, ZT + 7.4, 0.2, P, 20), { tone: "hi", className: "c-glass", crease: "none" }));
  out.push(D(k.corners(ant, 1.2).map(([x, y]) => at([x, y, ZT + 2.4])), { size: 0.35 }));
  return out.join("");
}

const WHISKERS = [-HX + 8, -HX + 30].flatMap((x) => [
  [[x, -YF + 2.6, ZT + 1.4], [x, -HW - 30, ZT + 1.4]],
  [[x, YF - 2.6, ZT + 1.4], [x, HW + 30, ZT + 1.4]],
]);
const whiskers = (side) =>
  WHISKERS.filter(([, b]) => Math.sign(b[1]) === side)
    .map(([a, b]) => `<g class="antenna">${k.wireSvg(at(a), at(b), { tone: "hi", size: 0.7 })}</g>`)
    .join("");

// +x end face: silver plate, camera with gold mount, RBF tag, heartbeat LED.
const CAM = G.frameAlong([XF, 0, 0], X);
function endFace() {
  const out = [];
  const pt = (y, z) => [XF + 0.05, y, z];
  out.push(poly([pt(-YF, ZB), pt(YF, ZB), pt(YF, ZT), pt(-YF, ZT)], "end-plate"));
  out.push(D([pt(-YF + 3.4, ZB + 3.4), pt(YF - 3.4, ZB + 3.4), pt(-YF + 3.4, ZT - 3.4), pt(YF - 3.4, ZT - 3.4)].map(at), { size: 0.45, tone: "mid" }));
  out.push(S(G.disc(0, 1.2, 11, CAM, P), { tone: "mid", className: "c-gold" }));
  out.push(D(G.dotsOf(CAM, 1.2, 9.6, 8, P, { all: true, phase: 0.2 }), { size: 0.4, tone: "hi" }));
  out.push(S(G.disc(1.2, 8.4, 7.6, CAM, P), { tone: "mid", className: "c-gun", inner: k.fadedSvg(G.ribsOf(CAM, 2.2, 7.4, 7.6, 40, P, { fade: [0.1, 0.5], seams: true }), { tone: "lo" }) }));
  out.push(S(G.disc(8.4, 9.4, 8.2, CAM, P), { tone: "hi", className: "c-silver" }));
  out.push(`<g data-part="lens">${S(G.disc(9.4, 9.7, 5.8, CAM, P), { tone: "hi", className: "c-glass", crease: "none" })}</g>`);
  out.push(Ln(G.circleOf(CAM, 9.7, 3.6, P), { tone: "hi", className: "glint" }));
  const y = YF - 4.6, z = ZB + 8;
  out.push(S(k.slabOf({ x: XF, y: y - 1.2, w: 2.4, d: 2.4, r: 0.4 }, z - 1.2, 2.4, P, 2), { tone: "mid", className: "c-red" }));
  out.push(poly([[XF + 2.6, y - 2.2, z - 1], [XF + 2.6, y + 2.2, z - 1], [XF + 2.6, y + 3, z - 14], [XF + 2.6, y - 3, z - 14]], "rbf-tag"));
  out.push(Ln(k.segment([XF + 2.6, y - 2.6, z - 10], [XF + 2.6, y + 2.6, z - 10], P), { tone: "hi", className: "rbf-line" }));
  const led = at(pt(-YF + 4.6, ZT - 8.4));
  out.push(`<circle data-part="led" class="led" cx="${led[0].toFixed(1)}" cy="${led[1].toFixed(1)}" r="0.8" opacity=".3"/>`);
  return out.join("");
}

// A deployable wing: two panels on gold hinge pins, tilted up toward the sun (8°).
function wing(side) {
  const out = [];
  const u0 = -WING.len / 2, u1 = WING.len / 2;
  for (let p = 0; p < 2; p++) {
    const v0 = p * (WING.depth + WING.between), v1 = v0 + WING.depth;
    const back = [wingPoint(side, u0, v0, 0), wingPoint(side, u1, v0, 0), wingPoint(side, u1, v1, 0), wingPoint(side, u0, v1, 0)];
    const front = [wingPoint(side, u0, v0, WING.t), wingPoint(side, u1, v0, WING.t), wingPoint(side, u1, v1, WING.t), wingPoint(side, u0, v1, WING.t)];
    // visible thickness: the outer long edge and the +x short edge
    out.push(poly([back[2], back[3], front[3], front[2]], "panel-edge"));
    out.push(poly([back[1], back[2], front[2], front[1]], "panel-edge"));
    out.push(poly(front, "panel-face"));
    const pt = (u, v) => wingPoint(side, u, v, WING.t + 0.02);
    out.push(cellField(pt, u0 + 1.4, u1 - 1.4, v0 + 1.4, v1 - 1.4, 8, 3));
  }
  // gold hinge pins along x: body-to-panel and panel-to-panel
  for (const v of [-WING.gap / 2 - 0.2, WING.depth + WING.between / 2]) {
    for (const x of [-36, 0, 36]) {
      const o = wingPoint(side, x - 4, v, WING.t / 2);
      out.push(S(G.disc(0, 8, 0.9, G.frameAlong(o, X), P), { tone: "mid", className: "c-gold" }));
    }
  }
  return out.join("");
}

// ---------------------------------------------------------------- colour
const COLOURS = {
  light: { silver: "#dfe3e8", gun: "#4f5560", gold: "#d9a535", copper: "#c9783c", ceramic: "#efe7d6", glass: "#0f2a4a", red: "#d63c2f",
    cells: "#8db3f2", grid: "rgba(255,255,255,.95)", fine: "rgba(255,255,255,.35)", rim: "#5b6b86", edge: "#9aa3b1", face: "#3b4250", plate: "#e7eaee",
    antenna: "#59606b", led: "#16a34a", glow: "#38bdf8", glint: "#5fd4ff", tag: "#ffe4e0" },
  dark: { silver: "#c9ced6", gun: "#454b55", gold: "#d6a43c", copper: "#c0763b", ceramic: "#d8cfbd", glass: "#0d2440", red: "#dc4a3d",
    cells: "#6f9be8", grid: "rgba(255,255,255,.85)", fine: "rgba(255,255,255,.28)", rim: "#c7d3ea", edge: "#7d8696", face: "#2f3540", plate: "#c3c8d0",
    antenna: "#e5e7eb", led: "#34d399", glow: "#5fd4ff", glint: "#7fe0ff", tag: "#ffd2cc" },
}[theme];
const C = COLOURS;
const tint = (name, c) =>
  `.${name}>.iso-fill,.${name}>.iso-top{fill:${c}}.${name}[data-seamless]>.iso-top{stroke:${c}}` +
  [92, 80, 66, 54].map((m, i) => `.${name}>.iso-shade[data-shade="${i}"]{fill:color-mix(in srgb,${c} ${m}%,#000)}.${name}[data-seamless]>.iso-shade[data-shade="${i}"]{stroke:color-mix(in srgb,${c} ${m}%,#000)}`).join("");
const PALETTE =
  ["silver", "gun", "gold", "copper", "ceramic", "glass", "red"].map((n) => tint("c-" + n, C[n])).join("") +
  `.cells{fill:${C.cells}}.cell-grid{stroke:${C.grid};stroke-width:.5;fill:none}.cell-fine{stroke:${C.fine};stroke-width:.22;fill:none}.cell-rim{fill:none;stroke:${C.rim};stroke-width:.4}` +
  `.panel-edge{fill:${C.edge}}.panel-face{fill:${C.face}}.end-plate{fill:${C.plate};stroke:${C.rim};stroke-width:.3}.mli{fill:${C.gold}}` +
  `.rbf-tag{fill:${C.red};stroke:${C.tag};stroke-width:.3}.iso-line.rbf-line{stroke:${C.tag}}.iso-line.glint{stroke:${C.glint};stroke-width:.8;opacity:.6}` +
  `.antenna .iso-line{stroke:${C.antenna};stroke-width:.7}.antenna .iso-wire-end{fill:${C.antenna}}.led{fill:${C.led};stroke:none}` +
  `.antenna.on .iso-line{stroke:${C.gold};stroke-width:.95}.antenna.on .iso-wire-end{fill:${C.gold}}[data-part="lens"].on path:not(.iso-line){fill:${C.glow}}`;

// ---------------------------------------------------------------- figure (back to front)
const svg = k.figureSvg({
  width: WIDTH,
  height: HEIGHT,
  label:
    "KHMER-SAT 1 as designed: a 3U CubeSat, 10 by 10 by 34 centimetres, with silver rails on its four long edges, solar cells on its faces and gold insulation strips at the unit joints. Two deployable solar wings, each of two panels on gold hinge pins, are tilted up toward the sun (8°). The top carries a UHF antenna module with four tape antennas, a GPS patch, a sun sensor and a small star tracker; the end face carries the Earth-observation camera, the rail-end deployment switches and a red remove-before-flight tag.",
  body: [
    `<style>${PALETTE}</style>`,
    wing(-1),
    whiskers(-1),
    rail(-HW, -HW),
    faces(),
    deck(),
    rail(-HW, HW - RAIL),
    endFace(),
    rail(HW - RAIL, -HW),
    rail(HW - RAIL, HW - RAIL),
    plungers(),
    whiskers(1),
    wing(1),
  ],
});

// ---------------------------------------------------------------- live: the flight software's modes
const live = `
const stage = document.querySelector(".iso-stage");
const svg = stage.querySelector("svg");
const lens = svg.querySelector('[data-part="lens"]');
const led = svg.querySelector('[data-part="led"]');
const antennas = [...svg.querySelectorAll(".antenna")];
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");
const STEPS = [
  { mode: "NOMINAL", text: "NOMINAL · wings charging", secs: 4 },
  { mode: "IMAGING", text: "IMAGING · 5 s capture hold", secs: 5 },
  { mode: "DOWNLINK", text: "DOWNLINK · image to ground", secs: 4 },
  { mode: "SAFE", text: "SAFE · minimum load", secs: 3 },
];
let step = 0, t = 0, frame = 0, last = 0, visible = false, auto = true, timer = 0, clock = 0;
function show() {
  const s = STEPS[step];
  if (readout.textContent !== s.text) readout.textContent = s.text;
  stage.setAttribute("aria-valuetext", s.text);
  lens.classList.toggle("on", s.mode === "IMAGING");
  antennas.forEach((a) => a.classList.toggle("on", s.mode === "DOWNLINK"));
}
function tick(now) {
  const dt = last ? Math.min((now - last) / 1000, 0.05) : 1 / 60;
  last = now; clock += dt;
  if (auto) { t += dt; if (t > STEPS[step].secs) { t = 0; step = (step + 1) % STEPS.length; } }
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
  fig: "Fig 2",
  title: "KHMER-SAT 1 · 3U design",
  hint: "Click to step through the modes",
  readout: "NOMINAL · wings charging",
  keys: [
    { mark: "blue", label: "Solar cells on the body and two deployable two-panel wings" },
    { mark: "lit", label: "Camera lights in IMAGING, UHF antennas in DOWNLINK" },
    { mark: "red", label: "Remove-before-flight tag, pulled before launch" },
  ],
  caption:
    "The 3U CubeSat as specified: 100 × 100 × 340.5 mm. Wing size, cell layout, antennas and optics are illustrative, because the real parts are still to be selected (docs/hardware-bom.md). The modes and the 5 s imaging hold are the flight software's own; the green LED on the end face blinks with the 1 s watchdog heartbeat.",
  body: `<div class="iso-stage" tabindex="0" role="button" aria-label="KHMER-SAT 1 3U CubeSat: Enter steps through the operating modes">${svg}</div>`,
});

const name = theme === "dark" ? "khmer-sat-1-3u-dark.html" : "khmer-sat-1-3u.html";
writeFileSync(join(HERE, name), k.pageHtml({ title: "KHMER-SAT 1 · 3U design", theme, body, script: kitScript() + live, width: 720 }));
console.log("wrote", name);
