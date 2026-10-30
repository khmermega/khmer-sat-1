// KHMER-SAT 1 bench prototype — isometric figure (anatomy kit).
//   node docs/figure/build.mjs           -> docs/figure/khmer-sat-1-prototype.html
//   node docs/figure/build.mjs --light   -> docs/figure/khmer-sat-1-prototype-light.html
// Every number the figure shows comes from MODEL below, which is taken from the
// project itself (onboard/config.py and sizes measured on synthetic frames).
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "./kit/iso-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const theme = process.argv.includes("--light") ? "light" : "dark";
const kitScript = () => readFileSync(join(HERE, "kit", "iso-kit.mjs"), "utf8").replace(/^export /gm, "");

// ---------------------------------------------------------------- truth
const MODEL = {
  chunk: 3072, // onboard/config.py chunk_size (bytes of image data per IMAGE_CHUNK)
  perTick: 40, // chunks_per_tick: chunks sent per 1 s onboard tick
  hold: 5, // imaging_hold_s
  heartbeat: 1, // the flight loop kicks the watchdog every 1 s tick
  // JPEG q85 sizes measured on the simulator's synthetic scenes (docs/budgets.md)
  modes: [
    { w: 640, h: 480, bytes: 32678 },
    { w: 1280, h: 960, bytes: 78665 },
    { w: 1920, h: 1440, bytes: 128202 },
    { w: 2592, h: 1944, bytes: 196206 },
  ],
};
MODEL.modes.forEach((m) => (m.chunks = Math.ceil(m.bytes / MODEL.chunk)));

// ---------------------------------------------------------------- world (1 unit ≈ 3 mm)
const WIDTH = 640;
const HEIGHT = 440;
const PLATE = { x: -164, y: -84, w: 290, d: 152, r: 8 };
const PLATE_H = 12;
const FOOT_H = 5;

const SAT = { x: -60, y: -30, w: 34, d: 34, r: 0.6 }; // 3U: 100 x 100 x 340.5 mm
const Z0 = 6; // pod top
const Z1 = Z0 + 114; // rail top
const POD = { x: -68, y: -38, w: 50, d: 50, r: 2.5 };
const RAIL = 3;
const LENS = [-43, -13];
const TOP = Z1 + 1.4;

const GS = { x: 28, y: -34, w: 80, d: 54, r: 3 }; // ground-station box
const GS_H = 22;
const DIAL = [52, -8];
const DIAL_R = 14;
const DIAL_TOP = GS_H + 5;
const KNOB = [90, -16];
const KNOB_R = 5;
const KNOB_TOP = GS_H + 5;
const DETENTS = MODEL.modes.map((_, i) => -Math.PI * 0.375 + (i * Math.PI * 0.75) / 3);

const PSU = { x: -154, y: -76, w: 54, d: 36, r: 3 };
const PSU_H = 28;

const P = k.fitProjection(
  [...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0), [LENS[0], LENS[1], TOP + 9], [-96, -34, Z1], [10, 8, Z1], [GS.x + GS.w, GS.y + GS.d, GS_H]],
  WIDTH,
  HEIGHT,
  { pad: 26, azimuth: 45 },
);

const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const depth = ([x, y, z = 0]) => k.depthOf([x, y, z], P);
const byDepth = (points) => [...points].sort((a, b) => depth(a) - depth(b));
const slab = (plan, z, h, tone = "mid", steps = 3, bevel = 0.4, extra = {}) => S(k.slabOf(plan, z, h, P, steps, bevel), { tone, ...extra });
const screws = (points, z, size = 0.45) => D(points.map(([x, y]) => at([x, y, z])), { size });

// ---------------------------------------------------------------- bench
function bench() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(PLATE, 22))) {
    out.push(S(k.cylinder(x, y, 7, -PLATE_H - FOOT_H, 1.6, P, 28), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 5.4, -PLATE_H - FOOT_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "mid" }));
  }
  out.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.6), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(PLATE, 5), 0, P), { tone: "lo" }));
  const corners = k.corners(PLATE, 10);
  out.push(L(corners.map(([x, y]) => k.ring(x, y, 2.2, 0, P, 16)).join(""), { tone: "lo" }));
  out.push(screws(corners, 0, 0.5));
  // ruler strip along the front edge, ticks rooted on its back edge
  const strip = { x: -88, y: PLATE.y + PLATE.d - 16, w: 196, d: 7, r: 1 };
  out.push(S(k.slabOf(strip, 0, 0.6, P, 3), { tone: "lo", crease: "none" }));
  const ticks = k.topTicks(strip.x + 4, strip.x + strip.w - 4, 4, 5, strip.y + 0.8, 0.6, [2, 3.6], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(screws([[strip.x + 2, strip.y + 3.5], [strip.x + strip.w - 2, strip.y + 3.5]], 0.6));
  // label plate with the one engraved label
  const label = { x: -150, y: PLATE.y + PLATE.d - 30, w: 52, d: 20, r: 1.2 };
  out.push(S(k.slabOf(label, 0, 0.8, P, 4, 0.3), { tone: "lo" }));
  out.push(L(k.planOutline(k.insetPlan(label, 1.6), 0.8, P, 4), { tone: "faint" }));
  out.push(k.faceTextSvg(k.topMatrix([label.x + 4, label.y + 7], 0.8, P, "x"), "KHMER-SAT 1 · EM", { size: 3.6, tone: "mid" }));
  for (const [y, len] of [[label.y + 11.5, 40], [label.y + 15, 28]]) {
    out.push(L(k.lineOnTop([label.x + 4, y], [label.x + 4 + len, y], 0.8, P), { tone: "lo", free: true }));
  }
  out.push(screws([[label.x + label.w - 3, label.y + 3], [label.x + label.w - 3, label.y + label.d - 3]], 0.8));
  return out.join("");
}

// ---------------------------------------------------------------- bench power supply
function psu() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PSU, 0, PSU_H, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(PSU, 5))) out.push(S(k.cylinder(x, y, 2.4, 0, 1.6, P, 16), { tone: "lo" }));
  const seam = k.sideSeam(PSU, PSU_H - 6, P, 6);
  out.push(S(k.slabOf(PSU, 1.6, PSU_H - 1.6, P, 6, 1), { tone: "mid", className: "c-psu", inner: L(seam, { tone: "faint" }) }));
  // display window (inlay) and two knurled knobs
  const win = { x: PSU.x + 5, y: PSU.y + PSU.d - 15, w: 22, d: 10, r: 1 };
  out.push(S(k.slabOf(win, PSU_H, 0.4, P, 3), { tone: "lo", flat: true, crease: "none" }));
  out.push(L(k.planOutline(k.insetPlan(win, 1.2), PSU_H + 0.4, P, 3), { tone: "faint" }));
  for (const [x, y] of byDepth([[PSU.x + 32, PSU.y + PSU.d - 10], [PSU.x + 42, PSU.y + PSU.d - 10]])) {
    out.push(S(k.cylinder(x, y, 3.4, PSU_H, 4, P, 24), { tone: "mid" }));
    out.push(L(k.knurl(x, y, 3.4, PSU_H, PSU_H + 4, 20, P, 0.3), { tone: "lo" }));
    out.push(D([at([x, y, PSU_H + 4])], { size: 0.5, tone: "hi" }));
  }
  // vent slots: closed outlines, no loose ends
  for (let i = 0; i < 5; i++) {
    out.push(L(k.planOutline({ x: PSU.x + 6 + i * 8, y: PSU.y + 4, w: 4.4, d: 12, r: 1.4 }, PSU_H, P, 3), { tone: "lo" }));
  }
  // binding posts (current-limited output to the satellite)
  for (const [x, y] of byDepth(POSTS)) {
    out.push(S(k.cylinder(x, y, 2.6, PSU_H, 1.4, P, 20), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 1.9, PSU_H + 1.4, 4, P, 20), { tone: "mid" }));
    out.push(L(k.knurl(x, y, 1.9, PSU_H + 1.4, PSU_H + 5.4, 12, P, 0.3), { tone: "lo" }));
  }
  out.push(screws(k.corners(PSU, 3), PSU_H, 0.4));
  return out.join("");
}
const POSTS = [[PSU.x + PSU.w - 12, PSU.y + PSU.d - 9], [PSU.x + PSU.w - 5, PSU.y + PSU.d - 9]];

// ---------------------------------------------------------------- test pod
function pod() {
  const out = [`<path class="iso-halo" d="${k.haloOf(POD, 0, Z0, P)}"/>`];
  out.push(S(k.slabOf(POD, 0, Z0, P, 4, 0.8), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(POD, 2.4), Z0, P, 4), { tone: "faint" }));
  // four corner clamps holding the rail feet
  for (const [x, y] of byDepth(k.corners(SAT, 1.5))) {
    out.push(slab({ x: x - 4.5, y: y - 4.5, w: 9, d: 9, r: 1 }, Z0, 2, "lo", 3, 0.3));
  }
  // umbilical connector for bench power
  out.push(slab(UMB, Z0, 3.2, "lo", 3, 0.3));
  out.push(D([at([UMB.x + 1.8, UMB.y + 2, Z0 + 3.2]), at([UMB.x + 1.8, UMB.y + 5, Z0 + 3.2])], { size: 0.5 }));
  out.push(screws(k.corners(POD, 3), Z0));
  return out.join("");
}
const UMB = { x: -66.5, y: -14, w: 4.4, d: 8, r: 0.6 };

// ---------------------------------------------------------------- the satellite (closed 3U body)
const railPlan = (cx, cy) => ({ x: cx, y: cy, w: RAIL, d: RAIL, r: 0.4 });
const RAILS = {
  far: railPlan(SAT.x, SAT.y),
  left: railPlan(SAT.x, SAT.y + SAT.d - RAIL),
  right: railPlan(SAT.x + SAT.w - RAIL, SAT.y),
  near: railPlan(SAT.x + SAT.w - RAIL, SAT.y + SAT.d - RAIL),
};
const BODY = k.insetPlan(SAT, 0.8); // side panels sit 0.8 inside the rails
const XF = BODY.x + BODY.w; // +x face (visible, right)
const YF = BODY.y + BODY.d; // +y face (visible, left)
const rail = (plan) => S(k.slabOf(plan, Z0 - 2, Z1 - Z0 + 3.4, P, 2, 0.3), { tone: "hi", crease: "lo", className: "c-alu" });
const poly = (points, cls) => `<path class="${cls}" d="M${points.map((p) => at(p).map((v) => v.toFixed(1)).join(" ")).join("L")}Z"/>`;

// A solar cell on a vertical face: chamfered corners, two bus bars, fingers that end on the outline.
function cellOn(face, u0, u1, z0, z1) {
  const c = 1.4;
  const pt = (u, z) => (face === "x" ? [XF + 0.05, u, z] : [u, YF + 0.05, z]);
  const outline = [pt(u0 + c, z0), pt(u1 - c, z0), pt(u1, z0 + c), pt(u1, z1 - c), pt(u1 - c, z1), pt(u0 + c, z1), pt(u0, z1 - c), pt(u0, z0 + c)];
  const out = [poly(outline, "cell")];
  const fingers = [];
  for (let z = z0 + 3; z < z1 - 2; z += 3) fingers.push(k.segment(pt(u0, z), pt(u1, z), P));
  out.push(`<path class="cell-finger" d="${fingers.join("")}"/>`);
  const bus = [u0 + (u1 - u0) / 3, u0 + (2 * (u1 - u0)) / 3].map((u) => k.segment(pt(u, z0), pt(u, z1), P)).join("");
  out.push(`<path class="cell-bus" d="${bus}"/>`);
  return out.join("");
}

function faceCells(face, skip = []) {
  const out = [];
  const lo = face === "x" ? BODY.y : BODY.x;
  const span = (face === "x" ? BODY.d : BODY.w) - 2 * RAIL + 1.6;
  const u0 = lo + RAIL - 0.8;
  for (let unit = 0; unit < 3; unit++) {
    const z0 = Z0 + 3 + unit * 38, z1 = z0 + 32;
    for (let col = 0; col < 2; col++) {
      if (skip.includes(unit * 2 + col)) continue;
      const a = u0 + 0.8 + col * (span / 2), b = a + span / 2 - 1.6;
      out.push(cellOn(face, a, b, z0, z1));
    }
  }
  return out.join("");
}

// Debug / umbilical port panel on the +y face, bottom unit: bench Ethernet + status LEDs.
const PORT = { u0: BODY.x + 18, u1: BODY.x + BODY.w - 3.4, z0: Z0 + 5, z1: Z0 + 31 };
function portPanel() {
  const pt = (u, z) => [u, YF + 0.1, z];
  const out = [poly([pt(PORT.u0, PORT.z0), pt(PORT.u1, PORT.z0), pt(PORT.u1, PORT.z1), pt(PORT.u0, PORT.z1)], "port")];
  // RJ45 socket: a closed outline, and a latch slot
  out.push(L(`M${[pt(PORT.u0 + 2, PORT.z0 + 15), pt(PORT.u1 - 2, PORT.z0 + 15), pt(PORT.u1 - 2, PORT.z0 + 22), pt(PORT.u0 + 2, PORT.z0 + 22)].map((p) => at(p).map((v) => v.toFixed(1)).join(" ")).join("L")}Z`, { tone: "mid" }));
  out.push(D([pt(PORT.u0 + 1.4, PORT.z1 - 1.4), pt(PORT.u1 - 1.4, PORT.z1 - 1.4), pt(PORT.u0 + 1.4, PORT.z0 + 1.4), pt(PORT.u1 - 1.4, PORT.z0 + 1.4)].map(at), { size: 0.4, tone: "hi" }));
  return out.join("");
}
const RJ45 = [(PORT.u0 + PORT.u1) / 2, YF + 0.1, PORT.z0 + 18.5];
const WDT_LED = [PORT.u0 + 2.6, YF + 0.2, PORT.z0 + 8];
const PWR_LED = [PORT.u0 + 5.6, YF + 0.2, PORT.z0 + 8];

// Remove-before-flight pin and its red tag on the +x face.
function rbf() {
  const y = BODY.y + 8, z = Z0 + 26;
  const out = [S(k.slabOf({ x: XF, y: y - 1.2, w: 2.6, d: 2.4, r: 0.4 }, z - 1.2, 2.4, P, 2), { tone: "mid", className: "c-red" })];
  const tag = [[XF + 2.8, y - 2.6, z - 1], [XF + 2.8, y + 2.6, z - 1], [XF + 2.8, y + 3.6, z - 17], [XF + 2.8, y - 3.6, z - 17]];
  out.push(poly(tag, "rbf-tag"));
  out.push(L(k.segment([XF + 2.8, y - 3.1, z - 13], [XF + 2.8, y + 3.1, z - 13], P), { tone: "hi", className: "rbf-line" }));
  return out.join("");
}

// Deployed solar wing, hinged on the top edge of a side face, lying flat.
function wing(side) {
  const plan = side > 0 ? { x: SAT.x + SAT.w + 1.2, y: SAT.y + 2, w: 34, d: SAT.d - 4, r: 0.6 } : { x: SAT.x - 35.2, y: SAT.y + 2, w: 34, d: SAT.d - 4, r: 0.6 };
  const z = Z1 - 1.6;
  const out = [`<path class="iso-halo" d="${k.haloOf(plan, z, 1.2, P)}" style="opacity:.35"/>`];
  out.push(S(k.slabOf(plan, z, 1.2, P, 2, 0.3), { tone: "mid", className: "c-panel" }));
  for (let i = 0; i < 2; i++) {
    for (let j = 0; j < 2; j++) {
      const cell = { x: plan.x + 1.4 + i * 16, y: plan.y + 1.4 + j * 13.2, w: 14.8, d: 11.8, r: 0.8 };
      out.push(`<path class="cell" d="${k.onTop(k.ringOf(cell, 2), z + 1.2, P, true)}"/>`);
      out.push(`<path class="cell-finger" d="${[3, 6, 9].map((dy) => k.lineOnTop([cell.x, cell.y + dy], [cell.x + cell.w, cell.y + dy], z + 1.2, P)).join("")}"/>`);
    }
  }
  // gold hinge knuckles on the body edge
  const hx = side > 0 ? SAT.x + SAT.w - 0.4 : SAT.x - 2;
  for (const y of [SAT.y + 6, SAT.y + SAT.d - 10]) out.push(S(k.slabOf({ x: hx, y, w: 2.4, d: 4, r: 0.5 }, z - 0.6, 2.4, P, 2, 0.2), { tone: "mid", className: "c-gold" }));
  return out.join("");
}

function topPanel() {
  const out = [S(k.slabOf(BODY, Z1 - 0.2, 1.6, P, 2, 0.3), { tone: "mid", crease: "lo", className: "c-panel" })];
  for (const [x, y] of [[BODY.x + 3, BODY.y + 3], [BODY.x + 3, BODY.y + 19.4]]) {
    const cell = { x, y, w: 9, d: 9.6, r: 0.6 };
    out.push(`<path class="cell" d="${k.onTop(k.ringOf(cell, 2), TOP, P, true)}"/>`);
  }
  // camera lens: gold mount ring, knurled barrel, glass
  const [x, y] = LENS;
  out.push(S(k.cylinder(x, y, 7.4, TOP, 1.4, P, 40), { tone: "mid", className: "c-gold" }));
  out.push(S(k.cylinder(x, y, 5.6, TOP + 1.4, 6, P, 40, 0.4), { tone: "mid", className: "c-dark" }));
  out.push(L(k.knurl(x, y, 5.6, TOP + 2.4, TOP + 6.4, 40, P, 0.3), { tone: "lo" }));
  out.push(S(k.cylinder(x, y, 4.4, TOP + 7.4, 0.2, P, 32), { tone: "mid", className: "c-gold", crease: "none" }));
  out.push(`<g data-part="glass">${S(k.cylinder(x, y, 3.2, TOP + 7.6, 0.3, P, 32), { tone: "hi", className: "c-glass", crease: "none" })}</g>`);
  out.push(screws([0, 1, 2, 3].map((i) => [x + 6.5 * Math.cos((i * Math.PI) / 2 + 0.6), y + 6.5 * Math.sin((i * Math.PI) / 2 + 0.6)]), TOP + 1.4, 0.35));
  // UHF antenna box + four deployed tape-spring whiskers along ±y
  const ant = { x: BODY.x + 22, y: BODY.y + 3, w: 8, d: BODY.d - 6, r: 0.6 };
  out.push(S(k.slabOf(ant, TOP, 2, P, 2, 0.3), { tone: "mid", className: "c-dark" }));
  for (const [y0, y1] of [[ant.y + 1.5, SAT.y - 18], [ant.y + ant.d - 1.5, SAT.y + SAT.d + 18]]) {
    for (const dx of [2, 6]) {
      const a = at([ant.x + dx, y0, TOP + 2]), b = at([ant.x + dx, y1, TOP + 2.4]);
      out.push(`<g class="antenna">${k.wireSvg(a, b, { tone: "hi", size: 0.6 })}</g>`);
    }
  }
  return out.join("");
}

function satellite() {
  const out = [];
  out.push(`<path class="iso-halo" d="${k.haloOf(SAT, Z0, 2, P)}" style="opacity:.5"/>`);
  out.push(wing(-1), rail(RAILS.far));
  out.push(S(k.slabOf(BODY, Z0, Z1 - Z0, P, 2), { tone: "mid", crease: "lo", className: "c-panel" }));
  out.push(faceCells("x"), faceCells("y", [1]), portPanel());
  // panel joints between the units run edge to edge on each face
  for (const z of [Z0 + 38, Z0 + 76]) out.push(L(k.segment([BODY.x, YF + 0.05, z], [XF, YF + 0.05, z], P) + k.segment([XF + 0.05, BODY.y, z], [XF + 0.05, YF, z], P), { tone: "lo" }));
  out.push(rail(RAILS.left), rail(RAILS.right), rail(RAILS.near));
  out.push(rbf());
  out.push(topPanel(), wing(1));
  out.push(`<circle data-part="wdt-led" class="ks-green" cx="${at(WDT_LED)[0].toFixed(1)}" cy="${at(WDT_LED)[1].toFixed(1)}" r="0.8" opacity="0.25"/>`);
  out.push(`<circle class="ks-amber" cx="${at(PWR_LED)[0].toFixed(1)}" cy="${at(PWR_LED)[1].toFixed(1)}" r="0.8"/>`);
  return out.join("");
}

// ---------------------------------------------------------------- ground station box
function ground() {
  const out = [`<path class="iso-halo" d="${k.haloOf(GS, 0, GS_H, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(GS, 6))) out.push(S(k.cylinder(x, y, 3, 0, 1.6, P, 16), { tone: "lo" }));
  const seam = k.sideSeam(GS, 6, P, 6);
  out.push(S(k.slabOf(GS, 1.6, GS_H - 1.6, P, 6, 1), { tone: "mid", className: "c-slate", inner: L(seam, { tone: "faint" }) }));
  out.push(L(k.planOutline(k.insetPlan(GS, 3.5), GS_H, P, 4), { tone: "faint" }));
  out.push(screws(k.corners(GS, 1.8), GS_H, 0.45));
  // RJ45 jack on the front face, where the bench link lands
  out.push(slab(GS_JACK, 6, 7, "lo", 2, 0.3));
  // vent slots
  for (let i = 0; i < 4; i++) out.push(L(k.planOutline({ x: GS.x + 50 + i * 6, y: GS.y + 30, w: 3.2, d: 14, r: 1.2 }, GS_H, P, 3), { tone: "lo" }));
  // chunk-counter dial
  const [dx, dy] = DIAL;
  out.push(S(k.cylinder(dx, dy, DIAL_R + 1.6, GS_H, 1.2, P, 56), { tone: "lo" }));
  out.push(S(k.cylinder(dx, dy, DIAL_R, GS_H + 1.2, DIAL_TOP - GS_H - 1.2, P, 64, 0.6), { tone: "hi", crease: "lo" }));
  out.push(L(k.ring(dx, dy, DIAL_R - 2, DIAL_TOP, P, 64), { tone: "lo" }));
  const ticks = k.radialTicks(dx, dy, DIAL_R - 2.4, 64, 8, DIAL_TOP, [1.2, 2.6], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(L(k.ring(dx, dy, 1.4, DIAL_TOP, P, 16), { tone: "mid" }));
  // resolution selector: knurled knob over a ring with four detents
  const [kx, ky] = KNOB;
  out.push(L(k.ring(kx, ky, 8.6, GS_H, P, 48), { tone: "lo" }));
  out.push(D(DETENTS.map((a) => at([kx + Math.sin(a) * 8.6, ky - Math.cos(a) * 8.6, GS_H])), { size: 0.7, tone: "mid" }));
  out.push(S(k.cylinder(kx, ky, KNOB_R, GS_H, KNOB_TOP - GS_H, P, 32, 0.4), { tone: "mid" }));
  out.push(L(k.knurl(kx, ky, KNOB_R, GS_H + 0.6, KNOB_TOP - 0.6, 30, P, 0.3), { tone: "lo" }));
  // link LED
  out.push(S(k.cylinder(LINK_LED[0], LINK_LED[1], 1.6, GS_H, 0.8, P, 16), { tone: "lo" }));
  return out.join("");
}
const GS_JACK = { x: 58, y: GS.y + GS.d - 0.4, w: 10, d: 2.2, r: 0.4 };
const LINK_LED = [100, -24];

const knobPointer = (angle) => k.lineOnTop([KNOB[0], KNOB[1]], [KNOB[0] + Math.sin(angle) * (KNOB_R - 0.8), KNOB[1] - Math.cos(angle) * (KNOB_R - 0.8)], KNOB_TOP + 0.1, P);
const needleAt = (turn) => {
  const a = turn * Math.PI * 2;
  return k.lineOnTop([DIAL[0] - Math.sin(a) * 3, DIAL[1] + Math.cos(a) * 3], [DIAL[0] + Math.sin(a) * (DIAL_R - 3.4), DIAL[1] - Math.cos(a) * (DIAL_R - 3.4)], DIAL_TOP + 0.2, P);
};

// ---------------------------------------------------------------- cables
const LINK_ROUTE = [
  RJ45,
  [RJ45[0], RJ45[1] + 6, RJ45[2]],
  [RJ45[0], RJ45[1] + 6, 0.4],
  [RJ45[0], 32, 0.4],
  [GS_JACK.x + 5, 32, 0.4],
  [GS_JACK.x + 5, GS_JACK.y + GS_JACK.d + 3, 0.4],
  [GS_JACK.x + 5, GS_JACK.y + GS_JACK.d + 3, 9.5],
  [GS_JACK.x + 5, GS_JACK.y + GS_JACK.d, 9.5],
];
const LINK_SCREEN = LINK_ROUTE.map(at);
const powerRoute = (dx) => [
  [POSTS[0][0] + dx, POSTS[0][1], PSU_H + 5.4],
  [POSTS[0][0] + dx, PSU.y + PSU.d + 2, PSU_H + 2],
  [POSTS[0][0] + dx, PSU.y + PSU.d + 4, 0.4],
  [UMB.x - 6 + dx * 0.3, UMB.y + 2 + dx * 0.4, 0.4],
  [UMB.x - 0.4, UMB.y + 2 + dx * 0.4, 3],
  [UMB.x + 1.8, UMB.y + 2 + dx * 0.4, Z0 + 3.2],
];
const wire = (route, tone) => {
  const s = route.map(at);
  return k.wireSvg(s[0], s[s.length - 1], { via: s.slice(1, -1), tone, size: 0.9 });
};


// ---------------------------------------------------------------- colour
// Materials, not decoration: blue cells on a navy substrate, aluminium rails, gold hinges and
// lens ring, a red remove-before-flight tag, colour-coded bench cables, amber chunks in flight.
const COLOURS = {
  dark: { panel: "#1d2b47", alu: "#a7b0bd", gold: "#d6a43c", dark: "#2b2f36", glass: "#5fd4ff", red: "#dc4a3d", psu: "#2e4a6b", slate: "#2a3342",
    cell: "#2c5fd8", cellEdge: "#9db8ff", finger: "rgba(200,215,255,.32)", bus: "rgba(225,232,250,.7)", port: "#0d1117", portEdge: "#6b7280",
    wRed: "#e5533f", wBlack: "#6b7280", wBlue: "#3b8bf6", antenna: "#e5e7eb", chunk: "#fbbf24", green: "#34d399", amber: "#fbbf24", tagLine: "#ffd2cc" },
  light: { panel: "#25365a", alu: "#c3c9d2", gold: "#d39a24", dark: "#3a3f47", glass: "#38bdf8", red: "#d63c2f", psu: "#4d6f96", slate: "#59657a",
    cell: "#2f63de", cellEdge: "#1e3a8a", finger: "rgba(225,235,255,.45)", bus: "rgba(240,244,255,.85)", port: "#1f2937", portEdge: "#4b5563",
    wRed: "#d63c2f", wBlack: "#222831", wBlue: "#2563eb", antenna: "#4b5563", chunk: "#f59e0b", green: "#16a34a", amber: "#f59e0b", tagLine: "#ffe4e0" },
}[theme];
const tint = (name, c) =>
  `.${name}>.iso-fill,.${name}>.iso-top{fill:${c}}` +
  [88, 74, 60, 48].map((m, i) => `.${name}>.iso-shade[data-shade="${i}"]{fill:color-mix(in srgb,${c} ${m}%,#000)}`).join("");
const C = COLOURS;
const PALETTE =
  ["panel", "alu", "gold", "dark", "glass", "red", "psu", "slate"].map((n) => tint("c-" + n, C[n])).join("") +
  `.cell{fill:${C.cell};stroke:${C.cellEdge};stroke-width:.35}.cell-finger{stroke:${C.finger};stroke-width:.25;fill:none}.cell-bus{stroke:${C.bus};stroke-width:.45;fill:none}` +
  `.port{fill:${C.port};stroke:${C.portEdge};stroke-width:.4}.rbf-tag{fill:${C.red};stroke:${C.tagLine};stroke-width:.3}.iso-line.rbf-line{stroke:${C.tagLine}}` +
  `.w-red .iso-line{stroke:${C.wRed};stroke-width:.9}.w-red .iso-wire-end{fill:${C.wRed}}.w-black .iso-line{stroke:${C.wBlack};stroke-width:.9}.w-black .iso-wire-end{fill:${C.wBlack}}` +
  `.w-blue .iso-line{stroke:${C.wBlue};stroke-width:1.1}.w-blue .iso-wire-end{fill:${C.wBlue}}.antenna .iso-line{stroke:${C.antenna};stroke-width:.5}.antenna .iso-wire-end{fill:${C.antenna}}` +
  `.ks-chunk{fill:${C.chunk};stroke:none}.ks-green{fill:${C.green};stroke:none}.ks-amber{fill:${C.amber};stroke:none}` +
  `.c-glass>.iso-top{fill:${C.glass}}`;

// ---------------------------------------------------------------- figure
const start = 1;
const svg = k.figureSvg({
  width: WIDTH,
  height: HEIGHT,
  label:
    "The KHMER-SAT 1 engineering prototype on a surface plate: a 3U CubeSat with blue solar cells on every face, two deployed solar wings, UHF antenna whiskers and a camera lens on its top panel, standing in a test pod with a red remove-before-flight tag. A bench power supply feeds the pod over red and black leads, and a blue Ethernet cable runs from the satellite's debug port to a ground-station box with a chunk-counter dial and a resolution selector. When a capture is commanded the lens lights for the imaging hold, then the image travels down the cable chunk by chunk and the dial counts them in.",
  body: [
    bench(),
    psu(),
    `<g class="w-black">${wire(powerRoute(0), "mid")}</g>`,
    `<g class="w-red">${wire(powerRoute(4), "mid")}</g>`,
    pod(),
    satellite(),
    ground(),
    `<g data-part="link" class="w-blue">${wire(LINK_ROUTE, "mid")}</g>`,
    `<style>${PALETTE}</style><g data-part="chunks"></g>`,
    `<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" d="${needleAt(0)}" style="stroke-width:1.1"/>`,
    `<path data-part="knob" class="iso-line" data-tone="hi" data-free="end" d="${knobPointer(DETENTS[start])}" style="stroke-width:1"/>`,
    `<circle data-part="link-led" class="ks-green" cx="${at([LINK_LED[0], LINK_LED[1], GS_H + 0.8])[0].toFixed(1)}" cy="${at([LINK_LED[0], LINK_LED[1], GS_H + 0.8])[1].toFixed(1)}" r="0.9" opacity="0.2"/>`,
  ],
});

// ---------------------------------------------------------------- live
const live = `
const P = ${JSON.stringify(P)};
const MODEL = ${JSON.stringify(MODEL)};
const DETENTS = ${JSON.stringify(DETENTS)};
const KNOB = ${JSON.stringify(KNOB)}, KNOB_R = ${KNOB_R}, KNOB_TOP = ${KNOB_TOP};
const DIAL = ${JSON.stringify(DIAL)}, DIAL_R = ${DIAL_R}, DIAL_TOP = ${DIAL_TOP};
const ROUTE = ${JSON.stringify(LINK_SCREEN)};
const knobPointer = ${knobPointer.toString().replaceAll("k.", "")};
const needleAt = ${needleAt.toString().replaceAll("k.", "")};
const stage = document.querySelector(".iso-stage");
const svg = stage.querySelector("svg");
const $ = (name) => svg.querySelector('[data-part="' + name + '"]');
const needle = $("needle"), knob = $("knob"), chunksLayer = $("chunks"), glass = $("glass"), wdt = $("wdt-led"), linkLed = $("link-led");
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");
// Playback: the imaging hold runs 5x fast, the downlink 5x slow (8 chunks per real second),
// so a whole cycle can be followed. The readout always shows simulated time and true counts.
const HOLD_SPEED = 5, CHUNK_RATE = MODEL.perTick / 5, TRAVEL = 1.4;
const segs = []; let total = 0;
for (let i = 1; i < ROUTE.length; i++) { const a = ROUTE[i - 1], b = ROUTE[i]; const len = Math.hypot(b[0] - a[0], b[1] - a[1]); segs.push({ a, b, len, at: total }); total += len; }
const along = (s) => { const d = Math.max(0, Math.min(1, s)) * total; const g = segs.find((x) => d <= x.at + x.len) || segs[segs.length - 1]; const f = g.len ? (d - g.at) / g.len : 0; return [g.a[0] + (g.b[0] - g.a[0]) * f, g.a[1] + (g.b[1] - g.a[1]) * f]; };
const dots = [...Array(64)].map(() => { const c = document.createElementNS("http://www.w3.org/2000/svg", "circle"); c.setAttribute("class", "ks-chunk"); c.setAttribute("r", "1.1"); c.setAttribute("opacity", "0"); chunksLayer.appendChild(c); return c; });
let res = ${start}, knobAngle = DETENTS[res], phase = "idle", t = 0, sent = 0, got = 0, shown = 0, clock = 0, idleFor = 0;
let frame = 0, last = 0, visible = false, touring = true, idleTimer = 0, flash = 0, blink = 0;
function capture() { if (phase !== "idle") return; phase = "imaging"; t = 0; sent = 0; got = 0; flash = 1; run(); }
function say() {
  const m = MODEL.modes[res];
  let text = m.w + "×" + m.h + " · " + m.chunks + " chunks · ";
  if (phase === "idle") text += "NOMINAL";
  if (phase === "imaging") text += "IMAGING " + Math.min(MODEL.hold, t * HOLD_SPEED).toFixed(1) + " / " + MODEL.hold + " s";
  if (phase === "downlink") text += "DOWNLINK " + got + " / " + m.chunks;
  if (phase === "verified") text += "SHA-256 ✓ · ACK";
  if (readout.textContent !== text) readout.textContent = text;
  stage.setAttribute("aria-valuetext", text);
}
function draw(dt) {
  knob.setAttribute("d", knobPointer(knobAngle));
  const m = MODEL.modes[res];
  shown += ((got / m.chunks) - shown) * (still.matches ? 1 : 1 - Math.exp(-dt / 0.12));
  needle.setAttribute("d", needleAt(phase === "idle" ? 0 : shown * (m.chunks / 64)));
  glass.style.opacity = String(0.55 + 0.45 * Math.max(flash, phase === "imaging" ? 0.6 : 0));
  const hb = (clock % MODEL.heartbeat) / MODEL.heartbeat;
  wdt.setAttribute("opacity", (0.2 + 0.8 * Math.exp(-hb * 7)).toFixed(2));
  linkLed.setAttribute("opacity", (0.2 + 0.8 * blink).toFixed(2));
  for (let i = 0; i < dots.length; i++) {
    const s = (t - i / CHUNK_RATE) / TRAVEL;
    const on = phase === "downlink" && i < sent && s < 1;
    if (!on) { if (dots[i].getAttribute("opacity") !== "0") dots[i].setAttribute("opacity", "0"); continue; }
    const [x, y] = along(s);
    dots[i].setAttribute("cx", x.toFixed(1)); dots[i].setAttribute("cy", y.toFixed(1));
    dots[i].setAttribute("opacity", Math.min(1, s * 8, (1 - s) * 8).toFixed(2));
  }
  say();
}
function tick(now) {
  const dt = last ? Math.min((now - last) / 1000, 1 / 20) : 1 / 60;
  last = now; clock += dt; t += dt;
  flash *= Math.exp(-dt / 0.35); blink *= Math.exp(-dt / 0.08);
  const m = MODEL.modes[res];
  knobAngle += (DETENTS[res] - knobAngle) * (still.matches ? 1 : 1 - Math.exp(-dt / 0.18));
  if (phase === "imaging" && t * HOLD_SPEED >= MODEL.hold) { phase = "downlink"; t = 0; }
  if (phase === "downlink") {
    sent = Math.min(m.chunks, Math.floor(t * CHUNK_RATE) + 1);
    const arrived = Math.min(m.chunks, Math.max(0, Math.floor((t - TRAVEL) * CHUNK_RATE) + 1));
    if (arrived > got) { got = arrived; blink = 1; }
    if (got >= m.chunks && t > TRAVEL + m.chunks / CHUNK_RATE) { phase = "verified"; t = 0; }
  }
  if (phase === "verified" && t > 1.8) { phase = "idle"; t = 0; idleFor = 0; }
  if (phase === "idle") { idleFor += dt; if (touring && idleFor > 1.6) { res = (res + 1) % MODEL.modes.length; capture(); } }
  draw(dt);
  frame = visible ? requestAnimationFrame(tick) : 0;
}
const run = () => { if (!frame && visible && !still.matches) { last = 0; frame = requestAnimationFrame(tick); } };
const hold = () => { touring = false; clearTimeout(idleTimer); idleTimer = setTimeout(() => { touring = true; run(); }, 6000); };
const pick = (i) => { if (phase !== "idle") return; res = Math.max(0, Math.min(MODEL.modes.length - 1, i)); if (still.matches) { knobAngle = DETENTS[res]; draw(1); } run(); };
new IntersectionObserver((e) => { visible = e[e.length - 1].isIntersecting; if (visible) run(); }, { rootMargin: "120px 0px" }).observe(stage);
stage.addEventListener("pointermove", (ev) => { const b = svg.getBoundingClientRect(); hold(); pick(Math.floor(((ev.clientX - b.left) / b.width) * MODEL.modes.length)); });
stage.addEventListener("click", () => { hold(); capture(); });
stage.addEventListener("keydown", (ev) => {
  if (ev.key === "ArrowRight" || ev.key === "ArrowUp") pick(res + 1);
  else if (ev.key === "ArrowLeft" || ev.key === "ArrowDown") pick(res - 1);
  else if (ev.key === "Enter" || ev.key === " ") capture();
  else return;
  ev.preventDefault(); hold();
});
if (still.matches) touring = false;
draw(1);
`;

const m0 = MODEL.modes[start];
const body = k.plateHtml({
  fig: "Fig 1",
  title: "KHMER-SAT 1 bench prototype",
  hint: "Hover: resolution · click: capture",
  readout: `${m0.w}×${m0.h} · ${m0.chunks} chunks · NOMINAL`,
  keys: [
    { mark: "lit", label: "Lens, chunks in flight and the counter needle: what moves when an image is taken" },
    { mark: "raised", label: "3U body: solar cells, deployed wings, UHF antennas, camera lens, RBF tag" },
    { mark: "blue", label: "Wired Ethernet bench link from the debug port (no RF); red/black: current-limited bench supply" },
  ],
  caption:
    "The engineering prototype on the bench, flight-like on the outside, wired to the ground station through its debug port. A capture holds the camera in IMAGING for 5 s, then the JPEG goes down the wired link in 3072-byte chunks, 40 per onboard tick, and the ground counts them in before checking the SHA-256 and sending the ACK. Chunk counts come from JPEG sizes measured on simulated scenes: 11, 26, 42 and 64 chunks for 640×480 up to 2592×1944. The green LED by the port blinks with the watchdog's 1 s heartbeat. Motion is re-timed so it can be followed: the hold runs 5× fast and the downlink 5× slow.",
  body: `<div class="iso-stage" tabindex="0" role="slider" aria-label="KHMER-SAT 1 bench prototype: arrow keys choose the resolution, Enter captures an image" aria-valuemin="0" aria-valuemax="3" aria-valuenow="${start}">${svg}</div>`,
});

const name = theme === "light" ? "khmer-sat-1-prototype-light.html" : "khmer-sat-1-prototype.html";
writeFileSync(join(HERE, name), k.pageHtml({ title: "KHMER-SAT 1 bench prototype", theme, body, script: kitScript() + live, width: 720 }));
console.log("wrote", name);
