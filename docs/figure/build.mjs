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
const LEVELS = [Z0, Z0 + 38, Z0 + 76, Z1 - 3]; // frame rings at unit boundaries
const BOARD = { x: -57, y: -27, w: 28, d: 28, r: 1 };
const PCB = 1.2;
const B = { eps: Z0 + 9, obc: Z0 + 46, wdt: Z0 + 62, cam: Z0 + 94 };
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
  [...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0), [LENS[0], LENS[1], TOP + 9], [GS.x + GS.w, GS.y + GS.d, GS_H]],
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
  out.push(S(k.slabOf(PSU, 1.6, PSU_H - 1.6, P, 6, 1), { tone: "mid", inner: L(seam, { tone: "faint" }) }));
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

// ---------------------------------------------------------------- the satellite
const railPlan = (cx, cy) => ({ x: cx, y: cy, w: RAIL, d: RAIL, r: 0.4 });
const RAILS = {
  far: railPlan(SAT.x, SAT.y),
  left: railPlan(SAT.x, SAT.y + SAT.d - RAIL),
  right: railPlan(SAT.x + SAT.w - RAIL, SAT.y),
  near: railPlan(SAT.x + SAT.w - RAIL, SAT.y + SAT.d - RAIL),
};
const rail = (plan) => S(k.slabOf(plan, Z0 - 2, Z1 - Z0 + 2, P, 2, 0.3), { tone: "hi", crease: "lo" });
const bars = (z, near) => {
  const along = near
    ? [{ x: SAT.x + RAIL, y: SAT.y + SAT.d - RAIL, w: SAT.w - 2 * RAIL, d: RAIL, r: 0.3 }, { x: SAT.x + SAT.w - RAIL, y: SAT.y + RAIL, w: RAIL, d: SAT.d - 2 * RAIL, r: 0.3 }]
    : [{ x: SAT.x + RAIL, y: SAT.y, w: SAT.w - 2 * RAIL, d: RAIL, r: 0.3 }, { x: SAT.x, y: SAT.y + RAIL, w: RAIL, d: SAT.d - 2 * RAIL, r: 0.3 }];
  return along.map((plan) => S(k.slabOf(plan, z, 3, P, 2, 0.3), { tone: "hi", crease: "lo" })).join("");
};

function backPanels() {
  // inner faces of the -x and -y side panels (solar cells face outward, away from us)
  const out = [];
  const back = { x: SAT.x + RAIL, y: SAT.y + 0.4, w: SAT.w - 2 * RAIL, d: 1, r: 0.2 };
  const left = { x: SAT.x + 0.4, y: SAT.y + RAIL, w: 1, d: SAT.d - 2 * RAIL, r: 0.2 };
  for (const plan of [left, back]) out.push(S(k.slabOf(plan, Z0, Z1 - Z0, P, 2), { tone: "lo", crease: "none" }));
  // stiffening ribs on the inner faces run full height, edge to edge
  for (const x of [SAT.x + 12, SAT.x + 22]) out.push(L(k.segment([x, SAT.y + 1.4, Z0], [x, SAT.y + 1.4, Z1], P), { tone: "faint" }));
  for (const y of [SAT.y + 12, SAT.y + 22]) out.push(L(k.segment([SAT.x + 1.4, y, Z0], [SAT.x + 1.4, y, Z1], P), { tone: "faint" }));
  return out.join("");
}

const standoffs = (z0, z1) => {
  const pts = k.corners(BOARD, 2.2);
  return pts.map(([x, y]) => ({ at: [x, y, z0], svg: S(k.cylinder(x, y, 0.8, z0, z1 - z0, P, 12), { tone: "mid", crease: "none" }) }));
};

function board(z, parts, gapTo) {
  // a PC/104-style card: the board, its parts and the four standoffs to the next card, by depth
  const items = [...parts, ...(gapTo ? standoffs(z + PCB, gapTo) : [])];
  items.sort((a, b) => depth(a.at) - depth(b.at));
  return S(k.slabOf(BOARD, z, PCB, P, 3, 0.3), { tone: "hi", crease: "lo" }) + items.map((i) => i.svg).join("");
}

const chip = (plan, z, h = 1, tone = "lo") => ({ at: [plan.x + plan.w / 2, plan.y + plan.d / 2, z], svg: slab(plan, z, h, tone, 2, 0.2) });

function epsBoard() {
  const z = B.eps + PCB;
  const cells = [[-50, -18], [-36, -18]].map(([x, y]) => ({
    at: [x, y, z],
    svg:
      S(k.cylinder(x, y, 4.4, z, 15, P, 28), { tone: "mid" }) +
      L([z + 2.5, z + 12.5].map((h) => k.sideArc(x, y, 4.4, h, P, 20)).join(""), { tone: "faint" }) +
      S(k.cylinder(x, y, 1.6, z + 15, 0.8, P, 14), { tone: "hi" }),
  }));
  const parts = [...cells, chip({ x: -54, y: -7, w: 9, d: 5, r: 0.5 }, z), chip({ x: -42, y: -7, w: 5, d: 5, r: 0.5 }, z), chip({ x: -34, y: -8, w: 3, d: 7, r: 0.4 }, z, 2, "mid")];
  return board(B.eps, parts, B.obc);
}

function obcBoard() {
  const z = B.obc + PCB;
  const parts = [
    chip({ x: -50, y: -21, w: 9, d: 9, r: 0.6 }, z, 1.4), // SoC
    chip({ x: -39, y: -21, w: 7, d: 4, r: 0.4 }, z), // RAM
    chip({ x: -39, y: -15, w: 5, d: 5, r: 0.4 }, z), // PMIC
    { at: [JACK.x + 4, JACK.y + 3, z], svg: slab(JACK, z, 6, "mid", 2, 0.4) + L(k.planOutline(k.insetPlan(JACK, 1.6), z + 6, P, 2), { tone: "lo" }) },
    { at: [-52, -6, z], svg: slab({ x: -55, y: -9, w: 6, d: 7, r: 0.5 }, z, 4, "mid", 2, 0.3) }, // USB
    { at: [-46, -25, z], svg: D(k.dotGrid(-54, -25.5, 14, 2, 1.6, z, P).map((p) => p), { size: 0.35, tone: "lo" }) }, // GPIO header
  ];
  return board(B.obc, parts, B.wdt);
}
const JACK = { x: -40, y: -6, w: 9, d: 7, r: 0.5 }; // RJ45 on the OBC's front edge

function wdtBoard() {
  const z = B.wdt + PCB;
  const pico = { x: -52, y: -23, w: 10, d: 20, r: 0.6 };
  const parts = [
    {
      at: [pico.x + 5, pico.y + 10, z],
      svg:
        slab(pico, z, 1, "mid", 2, 0.2) +
        slab({ x: pico.x + 3, y: pico.y + 7, w: 4, d: 4, r: 0.3 }, z + 1, 0.8, "lo", 2, 0.1) +
        D([...Array(8)].map((_, i) => at([pico.x + 0.7, pico.y + 1.5 + i * 2.4, z + 1])), { size: 0.3, tone: "lo" }) +
        D([...Array(8)].map((_, i) => at([pico.x + pico.w - 0.7, pico.y + 1.5 + i * 2.4, z + 1])), { size: 0.3, tone: "lo" }),
    },
    chip({ x: -38, y: -20, w: 6, d: 6, r: 0.4 }, z),
    chip({ x: -38, y: -11, w: 8, d: 3, r: 0.4 }, z, 1.6, "mid"), // load switch
  ];
  return board(B.wdt, parts, B.cam);
}
const WDT_LED = [-47, -4, B.wdt + PCB + 1];

function camBoard() {
  const z = B.cam + PCB;
  const parts = [
    { at: [LENS[0], LENS[1], z], svg: slab({ x: LENS[0] - 5, y: LENS[1] - 5, w: 10, d: 10, r: 0.6 }, z, 2.4, "lo", 2, 0.3) + L(k.ring(LENS[0], LENS[1], 3, z + 2.4, P, 24), { tone: "mid" }) },
    chip({ x: -55, y: -6, w: 6, d: 5, r: 0.4 }, z),
    chip({ x: -35, y: -6, w: 5, d: 5, r: 0.4 }, z),
  ];
  return board(B.cam, parts, null);
}

function topPanel() {
  const out = [S(k.slabOf(SAT, Z1, TOP - Z1, P, 2, 0.4), { tone: "mid", crease: "lo" })];
  // four solar cells around the lens
  for (const [x, y] of [[SAT.x + 2, SAT.y + 2], [SAT.x + 18, SAT.y + 2], [SAT.x + 2, SAT.y + 18], [SAT.x + 18, SAT.y + 18]]) {
    const cell = { x, y, w: 14, d: 14, r: 0.6 };
    out.push(L(k.planOutline(cell, TOP, P, 2), { tone: "lo" }));
    out.push(L([4.5, 9.5].map((dy) => k.lineOnTop([x, y + dy], [x + 14, y + dy], TOP, P)).join(""), { tone: "faint" }));
  }
  out.push(screws(k.corners(SAT, 1.5), TOP, 0.4));
  // camera lens: mount ring, knurled focus barrel, glass (the lit part)
  const [x, y] = LENS;
  out.push(S(k.cylinder(x, y, 7.4, TOP, 1.4, P, 40), { tone: "lo" }));
  out.push(S(k.cylinder(x, y, 5.6, TOP + 1.4, 6, P, 40, 0.4), { tone: "mid" }));
  out.push(L(k.knurl(x, y, 5.6, TOP + 2.4, TOP + 6.4, 40, P, 0.3), { tone: "lo" }));
  out.push(L(k.ring(x, y, 4.4, TOP + 7.4, P, 32), { tone: "lo" }));
  out.push(`<g data-part="glass">${S(k.cylinder(x, y, 3.2, TOP + 7.4, 0.3, P, 32), { tone: "hi", lit: true, crease: "none" })}</g>`);
  out.push(screws([0, 1, 2, 3].map((i) => [x + 6.5 * Math.cos(i * Math.PI / 2 + 0.6), y + 6.5 * Math.sin(i * Math.PI / 2 + 0.6)]), TOP + 1.4, 0.35));
  return out.join("");
}

function satellite() {
  const out = [];
  out.push(rail(RAILS.far), backPanels(), bars(LEVELS[0], false), rail(RAILS.left), rail(RAILS.right), bars(LEVELS[0], true));
  out.push(epsBoard());
  out.push(bars(LEVELS[1], false), bars(LEVELS[1], true));
  out.push(obcBoard(), wdtBoard());
  out.push(bars(LEVELS[2], false), bars(LEVELS[2], true));
  out.push(camBoard());
  out.push(bars(LEVELS[3], false), bars(LEVELS[3], true));
  out.push(rail(RAILS.near), topPanel());
  // watchdog heartbeat LED (pulses live)
  out.push(`<circle data-part="wdt-led" class="ks-lit" cx="${at(WDT_LED)[0].toFixed(1)}" cy="${at(WDT_LED)[1].toFixed(1)}" r="0.9" opacity="0.25"/>`);
  return out.join("");
}

// ---------------------------------------------------------------- ground station box
function ground() {
  const out = [`<path class="iso-halo" d="${k.haloOf(GS, 0, GS_H, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(GS, 6))) out.push(S(k.cylinder(x, y, 3, 0, 1.6, P, 16), { tone: "lo" }));
  const seam = k.sideSeam(GS, 6, P, 6);
  out.push(S(k.slabOf(GS, 1.6, GS_H - 1.6, P, 6, 1), { tone: "mid", inner: L(seam, { tone: "faint" }) }));
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
  [JACK.x + 4.5, JACK.y + JACK.d, B.obc + PCB + 3],
  [JACK.x + 4.5, 16, B.obc + PCB + 3],
  [JACK.x + 4.5, 16, 0.4],
  [JACK.x + 4.5, 32, 0.4],
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

// ---------------------------------------------------------------- figure
const start = 1;
const svg = k.figureSvg({
  width: WIDTH,
  height: HEIGHT,
  label:
    "The KHMER-SAT 1 engineering prototype on a surface plate. An open 3U CubeSat frame stands in a test pod with its board stack showing: power board with two cells, the Raspberry Pi onboard computer, the watchdog microcontroller and the camera board under a lens on the top panel. A bench power supply feeds the pod, and a wired Ethernet link runs to a ground-station box with a chunk-counter dial and a resolution selector. When a capture is commanded the lens lights for the imaging hold, then the image travels down the cable chunk by chunk and the dial counts them in.",
  body: [
    bench(),
    psu(),
    wire(powerRoute(0), "lo"),
    wire(powerRoute(4), "lo"),
    pod(),
    satellite(),
    ground(),
    `<g data-part="link">${wire(LINK_ROUTE, "mid")}</g>`,
    `<style>.ks-lit{fill:var(--anatomy-lit);stroke:none}</style><g data-part="chunks"></g>`,
    `<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" d="${needleAt(0)}" style="stroke-width:1.1"/>`,
    `<path data-part="knob" class="iso-line" data-tone="hi" data-free="end" d="${knobPointer(DETENTS[start])}" style="stroke-width:1"/>`,
    `<circle data-part="link-led" class="ks-lit" cx="${at([LINK_LED[0], LINK_LED[1], GS_H + 0.8])[0].toFixed(1)}" cy="${at([LINK_LED[0], LINK_LED[1], GS_H + 0.8])[1].toFixed(1)}" r="0.9" opacity="0.2"/>`,
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
const dots = [...Array(64)].map(() => { const c = document.createElementNS("http://www.w3.org/2000/svg", "circle"); c.setAttribute("class", "ks-lit"); c.setAttribute("r", "1.1"); c.setAttribute("opacity", "0"); chunksLayer.appendChild(c); return c; });
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
    { mark: "raised", label: "Board stack: power, onboard computer, watchdog MCU, camera" },
    { mark: "dotted", label: "Wired bench link (no RF) and current-limited bench supply" },
  ],
  caption:
    "The engineering prototype on the bench. A capture holds the camera in IMAGING for 5 s, then the JPEG goes down the wired link in 3072-byte chunks, 40 per onboard tick, and the ground counts them in before checking the SHA-256 and sending the ACK. Chunk counts come from JPEG sizes measured on simulated scenes: 11, 26, 42 and 64 chunks for 640×480 up to 2592×1944. The watchdog LED blinks with the 1 s heartbeat. Motion is re-timed so it can be followed: the hold runs 5× fast and the downlink 5× slow.",
  body: `<div class="iso-stage" tabindex="0" role="slider" aria-label="KHMER-SAT 1 bench prototype: arrow keys choose the resolution, Enter captures an image" aria-valuemin="0" aria-valuemax="3" aria-valuenow="${start}">${svg}</div>`,
});

const name = theme === "light" ? "khmer-sat-1-prototype-light.html" : "khmer-sat-1-prototype.html";
writeFileSync(join(HERE, name), k.pageHtml({ title: "KHMER-SAT 1 bench prototype", theme, body, script: kitScript() + live, width: 720 }));
console.log("wrote", name);
