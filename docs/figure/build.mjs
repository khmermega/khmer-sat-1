// KHMER-SAT 1 — concept illustration of the satellite (anatomy kit).
//   node docs/figure/build.mjs           -> docs/figure/khmer-sat-1-prototype.html        (light, white page)
//   node docs/figure/build.mjs --dark    -> docs/figure/khmer-sat-1-prototype-dark.html
// A conventional satellite look: a turned cylindrical bus with insulation bands and radiators,
// an Earth-observation camera, a dish antenna and two sun-tracking solar wings on booms.
// It is a concept illustration, not the 3U CubeSat design and not to scale.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "./kit/iso-kit.mjs";
import * as G from "./kit/lathe.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const theme = process.argv.includes("--dark") ? "dark" : "light";
const kitScript = () => readFileSync(join(HERE, "kit", "iso-kit.mjs"), "utf8").replace(/^export /gm, "");

const WIDTH = 640;
const HEIGHT = 420;

// Bus axis along +x; angle 0 points to +y, 90° to +z.
const F = G.frameOf([0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]);
const DISH = { vertex: 37, focal: 15, R: 30 };
const DISH_RIM = DISH.vertex + (DISH.R * DISH.R) / (4 * DISH.focal);
const FEED = DISH.vertex + DISH.focal;
const BOOM_S = -26; // booms leave the main body here
const WING = { from: 32, to: 126, half: 19, tilt: (52 * Math.PI) / 180, t: 0.9 };

const P = k.fitProjection(
  [
    [-66, 0, 18], [-66, 0, -18], [DISH_RIM, 0, 31], [DISH_RIM, 0, -31], [FEED + 4, 0, 0],
    ...[-1, 1].flatMap((side) => [WING.from, WING.to].flatMap((v) => [-1, 1].map((u) => wingPoint(side * v, u * WING.half, 0)))),
  ],
  WIDTH,
  HEIGHT,
  { pad: 24, azimuth: 38, elevation: 26 },
);

function wingPoint(v, u, n) {
  // plane through the boom axis (x = BOOM_S, z = 0), rotated about y by the tilt
  const d = [Math.cos(WING.tilt), 0, -Math.sin(WING.tilt)];
  const nn = [Math.sin(WING.tilt), 0, Math.cos(WING.tilt)];
  return [BOOM_S + d[0] * u + nn[0] * n, v, d[2] * u + nn[2] * n];
}

const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const Ln = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const poly = (points, cls) => `<path class="${cls}" d="M${points.map((p) => at(p).map((v) => v.toFixed(1)).join(" ")).join("L")}Z"/>`;
const seam = (s, r, slope = 0) => Ln(G.arcOf(F, s, r, P, { slope }), { tone: "faint" });

// ---------------------------------------------------------------- bus
function bus() {
  const out = [];
  // aft: thruster nozzle and propulsion ring
  out.push(S(G.solidOf([[-66, 7.5, 1], [-62, 5.4, 1], [-58, 4.2]], F, P), { tone: "mid", className: "c-gun" }));
  out.push(S(G.disc(-58, -50, 13, F, P), { tone: "mid", className: "c-gun", inner: seam(-54, 13) }));
  out.push(D(G.dotsOf(F, -50, 11.4, 16, P, { fade: [0.04, 0.42] }), { size: 0.4, tone: "hi" }));
  // main body: silver drum with radiator fins, wrapped in a copper insulation band
  const ribs = k.fadedSvg(G.ribsOf(F, -50, -40, 17, 40, P, { fade: [0.08, 0.5], seams: true }), { tone: "lo" });
  // drawn back to front in sections, so no end cap paints over a nearer section
  out.push(S(G.disc(-50, -34, 17, F, P), { tone: "hi", className: "c-silver", inner: ribs }));
  out.push(S(G.disc(-34, -22, 17.5, F, P), { tone: "mid", className: "c-copper", inner: seam(-28, 17.5) }));
  out.push(S(G.disc(-22, -6, 17, F, P), { tone: "hi", className: "c-silver", inner: seam(-14, 17) }));
  // separation ring
  out.push(S(G.disc(-6, -2, 18.4, F, P), { tone: "mid", className: "c-gold" }));
  out.push(D(G.dotsOf(F, -2, 16.6, 24, P, { fade: [0.04, 0.42] }), { size: 0.4, tone: "hi" }));
  // avionics drum with a gold foil band and equipment hatch seams
  out.push(S(G.disc(-2, 24, 15.5, F, P), { tone: "hi", className: "c-silver", inner: seam(8, 15.5) + seam(20, 15.5) }));
  out.push(S(G.disc(24, 30, 15.8, F, P), { tone: "mid", className: "c-gold", inner: seam(27, 15.8) }));
  out.push(k.fadedSvg(G.ribsOf(F, 8, 20, 15.5, 18, P, { fade: [0.15, 0.6], phase: 0.2 }), { tone: "lo" }));
  return out.join("");
}


// Equipment mounted on the bus surface: boxes, dark radiator tiles, a star tracker.
const V = G.viewOf(P);
const facing = G.angleToward(F, V);
function boxOn(s, r, ang, w, d, h, cls, tone = "mid") {
  const a = G.radialOf(F, ang);
  const Bf = G.frameOf(G.pointOf(F, s, r - 0.4, ang), a, [1, 0, 0], G.cross3(a, [1, 0, 0]));
  return S(G.prismOf(Bf, [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]], 0, h, P), { tone, className: cls });
}
function equipment() {
  const out = [];
  // avionics boxes on the aft drum
  out.push(boxOn(-45, 17, facing - 0.55, 8, 6, 3, "c-gun"));
  out.push(boxOn(-44, 17, facing + 0.35, 6, 5, 2.4, "c-gold"));
  out.push(boxOn(-12, 17, facing + 0.05, 7, 8, 2, "c-gun"));
  // dark radiator tiles on the avionics drum
  for (const [s0, da] of [[3, -0.5], [3, 0.25], [14, -0.12]]) out.push(boxOn(s0 + 3, 15.5, facing + da + 0.9, 7, 6.4, 0.5, "c-rad", "lo"));
  // star tracker on top with a gold baffle
  const top = Math.PI / 2 + 0.25;
  const T = G.frameAlong(G.pointOf(F, -10, 16.6, top), G.radialOf(F, top));
  out.push(S(G.disc(0, 3, 3, T, P), { tone: "mid", className: "c-gun" }));
  out.push(S(G.solidOf([[3, 2.2], [7, 3.4]], T, P, { fill: "hull" }), { tone: "mid", className: "c-gold" }));
  return out.join("");
}

// Earth-observation camera on the side of the avionics drum, facing the viewer.
function camera() {
  const ang = G.angleToward(F, G.viewOf(P)) - 0.35;
  const o = G.pointOf(F, 2.6 + 11, 15.2, ang);
  const C = G.frameAlong(o, G.radialOf(F, ang));
  return (
    S(G.disc(0, 1.6, 6.4, C, P), { tone: "mid", className: "c-gold" }) +
    S(G.disc(1.6, 6.5, 4.6, C, P), { tone: "mid", className: "c-gun", inner: k.fadedSvg(G.ribsOf(C, 2.4, 5.6, 4.6, 26, P, { fade: [0.1, 0.5], seams: true }), { tone: "lo" }) }) +
    `<g data-part="lens">${S(G.disc(6.5, 6.8, 3.3, C, P), { tone: "hi", className: "c-glass", crease: "none" })}</g>`
  );
}

// Dish antenna: a thin paraboloid shell seen from its open side, with a feed on three struts.
function dish() {
  const out = [];
  out.push(S(G.disc(30, 33, 8, F, P), { tone: "mid", className: "c-gun" }));
  out.push(S(G.disc(33, DISH.vertex + 0.6, 10.5, F, P), { tone: "mid", className: "c-silver" }));
  const outer = [], inner = [];
  for (let i = 0; i <= 16; i++) {
    const r = (DISH.R * i) / 16;
    outer.push([DISH.vertex + (r * r) / (4 * DISH.focal), r, 1]);
    inner.push([DISH.vertex + 0.9 + (r * r) / (4 * DISH.focal), Math.max(0, r - 0.0), 1]);
  }
  const meridian = [...outer, [DISH_RIM + 0.9, DISH.R], ...inner.reverse()];
  out.push(S(G.lathe(meridian, F, P, { fill: "facets", smooth: true }), { tone: "hi", className: "c-dish", crease: "none" }));
  out.push(Ln(G.circleOf(F, DISH_RIM + 0.45, DISH.R, P), { tone: "mid" }));
  out.push(Ln(G.circleOf(F, DISH.vertex + 0.9 + (18 * 18) / (4 * DISH.focal), 18, P), { tone: "faint" }));
  // struts from the rim to the feed horn
  const feed = [FEED, 0, 0];
  for (const a of [Math.PI / 2, (7 * Math.PI) / 6, (11 * Math.PI) / 6]) {
    out.push(`<g class="strut">${k.wireSvg(at(G.pointOf(F, DISH_RIM + 0.6, DISH.R - 0.6, a)), at(feed), { tone: "mid", size: 0.6, ends: "from" })}</g>`);
  }
  out.push(S(G.solidOf([[FEED - 2.5, 1.2], [FEED + 1.5, 2.8], [FEED + 2.5, 2.8]], F, P), { tone: "mid", className: "c-gun" }));
  out.push(`<g data-part="feed">${S(G.disc(FEED + 2.5, FEED + 2.8, 2.6, F, P), { tone: "hi", className: "c-dish", crease: "none" })}</g>`);
  return out.join("");
}

// Solar wing on a boom, tilted toward the sun: a thin panel with a cell grid.
function wing(side) {
  const out = [];
  const B = G.frameAlong([BOOM_S, 0, 0], [0, side, 0]);
  out.push(S(G.disc(16.8, WING.from + 1, 1.5, B, P), { tone: "mid", className: "c-silver" }));
  out.push(S(G.disc(17, 21, 3.4, B, P), { tone: "mid", className: "c-gold" })); // drive (SADA)
  out.push(S(G.disc(WING.from - 3, WING.from, 2.6, B, P), { tone: "mid", className: "c-gun" })); // yoke
  const v0 = side * WING.from, v1 = side * WING.to;
  const corners = (n) => [wingPoint(v0, -WING.half, n), wingPoint(v1, -WING.half, n), wingPoint(v1, WING.half, n), wingPoint(v0, WING.half, n)];
  // panel edge (thickness) then the cell face
  out.push(poly([...corners(-WING.t), ...corners(0).reverse()].slice(0, 4), "panel-edge"));
  out.push(poly(corners(0), "panel-edge"));
  out.push(poly(corners(WING.t), "cells"));
  // cell grid: lines run edge to edge
  const grid = [];
  const cols = 9, rows = 3;
  for (let i = 1; i < cols; i++) {
    const v = v0 + ((v1 - v0) * i) / cols;
    grid.push(k.segment(wingPoint(v, -WING.half, WING.t), wingPoint(v, WING.half, WING.t), P));
  }
  for (let j = 1; j < rows; j++) {
    const u = -WING.half + (2 * WING.half * j) / rows;
    grid.push(k.segment(wingPoint(v0, u, WING.t), wingPoint(v1, u, WING.t), P));
  }
  out.push(`<path class="cell-grid" d="${grid.join("")}"/>`);
  const fine = [];
  for (let i = 0; i < cols * 4; i++) {
    if (i % 4 === 0) continue;
    const v = v0 + ((v1 - v0) * i) / (cols * 4);
    fine.push(k.segment(wingPoint(v, -WING.half, WING.t), wingPoint(v, WING.half, WING.t), P));
  }
  out.push(`<path class="cell-fine" d="${fine.join("")}"/>`);
  out.push(`<path class="panel-rim" d="M${corners(WING.t).map((p) => at(p).map((x) => x.toFixed(1)).join(" ")).join("L")}Z"/>`);
  return out.join("");
}

// ---------------------------------------------------------------- colour
const COLOURS = {
  light: { silver: "#dfe3e8", gun: "#5b616b", gold: "#d9a535", copper: "#c9783c", dish: "#f4f5f7", glass: "#0f2a4a", rad: "#262b33",
    cells: "#8db3f2", grid: "rgba(255,255,255,.95)", fine: "rgba(255,255,255,.35)", edge: "#9aa3b1", rim: "#5b6b86", strut: "#7b8494", glow: "#38bdf8" },
  dark: { silver: "#c9ced6", gun: "#4b515a", gold: "#d6a43c", copper: "#c0763b", dish: "#e6e8ec", glass: "#0d2440", rad: "#20252c",
    cells: "#6f9be8", grid: "rgba(255,255,255,.85)", fine: "rgba(255,255,255,.28)", edge: "#7d8696", rim: "#c7d3ea", strut: "#aeb6c3", glow: "#5fd4ff" },
}[theme];
const C = COLOURS;
const tint = (name, c) =>
  `.${name}>.iso-fill,.${name}>.iso-top{fill:${c}}.${name}[data-seamless]>.iso-top{stroke:${c}}` +
  [92, 80, 66, 54].map((m, i) => `.${name}>.iso-shade[data-shade="${i}"]{fill:color-mix(in srgb,${c} ${m}%,#000)}.${name}[data-seamless]>.iso-shade[data-shade="${i}"]{stroke:color-mix(in srgb,${c} ${m}%,#000)}`).join("");
const PALETTE =
  ["silver", "gun", "gold", "copper", "dish", "glass", "rad"].map((n) => tint("c-" + n, C[n])).join("") +
  `.cells{fill:${C.cells}}.panel-edge{fill:${C.edge}}.panel-rim{fill:none;stroke:${C.rim};stroke-width:.5}.cell-grid{stroke:${C.grid};stroke-width:.55;fill:none}.cell-fine{stroke:${C.fine};stroke-width:.25;fill:none}` +
  `.strut .iso-line{stroke:${C.strut};stroke-width:.6}.strut .iso-wire-end{fill:${C.strut}}` +
  `[data-part="feed"].on path:not(.iso-line),[data-part="lens"].on path:not(.iso-line){fill:${C.glow}}`;

// ---------------------------------------------------------------- figure (back to front)
const svg = k.figureSvg({
  width: WIDTH,
  height: HEIGHT,
  label:
    "Concept illustration of KHMER-SAT 1: a silver cylindrical satellite bus with a thruster at the back, radiator fins, a copper insulation band, a gold separation ring and an avionics drum carrying an Earth-observation camera. A white dish antenna with a feed on three struts sits at the front, and two blue solar wings on booms are tilted toward the sun.",
  body: [`<style>${PALETTE}</style>`, wing(-1), bus(), equipment(), camera(), dish(), wing(1)],
});

// ---------------------------------------------------------------- live: the flight software's modes
const live = `
const stage = document.querySelector(".iso-stage");
const svg = stage.querySelector("svg");
const lens = svg.querySelector('[data-part="lens"]');
const feed = svg.querySelector('[data-part="feed"]');
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");
const STEPS = [
  { mode: "NOMINAL", text: "NOMINAL · wings charging", secs: 4 },
  { mode: "IMAGING", text: "IMAGING · 5 s capture hold", secs: 5 },
  { mode: "DOWNLINK", text: "DOWNLINK · image to ground", secs: 4 },
  { mode: "SAFE", text: "SAFE · minimum load", secs: 3 },
];
let step = 0, t = 0, frame = 0, last = 0, visible = false, auto = true, timer = 0;
function show() {
  const s = STEPS[step];
  if (readout.textContent !== s.text) readout.textContent = s.text;
  stage.setAttribute("aria-valuetext", s.text);
  lens.classList.toggle("on", s.mode === "IMAGING");
  feed.classList.toggle("on", s.mode === "DOWNLINK");
}
function tick(now) {
  const dt = last ? Math.min((now - last) / 1000, 0.05) : 1 / 60;
  last = now;
  if (auto) { t += dt; if (t > STEPS[step].secs) { t = 0; step = (step + 1) % STEPS.length; } }
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
  title: "KHMER-SAT 1 · concept",
  hint: "Click to step through the modes",
  readout: "NOMINAL · wings charging",
  keys: [
    { mark: "blue", label: "Sun-tracking solar wings on booms" },
    { mark: "lit", label: "Camera lights in IMAGING, dish feed in DOWNLINK" },
  ],
  caption:
    "Concept illustration in a conventional satellite style, not the 3U CubeSat design and not to scale. The real KHMER-SAT 1 is specified as a 3U CubeSat (100 × 100 × 340.5 mm); its antenna, optics and solar arrays are still to be selected. The modes and the 5 s imaging hold are the flight software's own.",
  body: `<div class="iso-stage" tabindex="0" role="button" aria-label="KHMER-SAT 1 concept: Enter steps through the operating modes">${svg}</div>`,
});

const name = theme === "dark" ? "khmer-sat-1-prototype-dark.html" : "khmer-sat-1-prototype.html";
writeFileSync(join(HERE, name), k.pageHtml({ title: "KHMER-SAT 1 · concept", theme, body, script: kitScript() + live, width: 720 }));
console.log("wrote", name);
