// Build EcoShield-Delhi.pptx — native PowerPoint deck for the project.
// Forest/emerald palette, shape-based visuals (no icon fonts), inch-precise
// layout on a 13.33 x 7.5 canvas to avoid overflow/overlap glitches.
const pptxgen = require("pptxgenjs");

const C = {
  forest: "04241A", green: "006948", greenMid: "00855D", mint: "68DBA9", mint2: "85F8C4",
  indigo: "4B41E1", indigoLite: "EEF0FF", indigoInk: "3323CC",
  ink: "191C1E", muted: "3D4A42", soft: "6D7A72", bg: "F7F9FB", card: "FFFFFF",
  line: "BCCAC0", slate: "E0E3E5",
  teal: "0EA5A4", tealLite: "DFF5F3", tealInk: "0F6E56",
  error: "BA1A1A", errLite: "FBEAEA", errInk: "93000A",
  amber: "B45309", amberLite: "FAEEDA",
  coral: "D85A30", coralLite: "FAECE7", coralInk: "712B13",
  blue: "185FA5", blueLite: "EAF1FB",
};
const W = 13.33, H = 7.5, M = 0.7;
const FH = "Georgia", FB = "Calibri", FM = "Consolas";
const sh = () => ({ type: "outer", color: "000000", blur: 7, offset: 3, angle: 135, opacity: 0.10 });

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "krishiv47";
pres.title = "EcoShield Delhi — Agentic AI Pollution-Control System";

function footer(s, n) {
  s.addShape(pres.shapes.LINE, { x: M, y: 7.02, w: W - 2 * M, h: 0, line: { color: C.slate, width: 1 } });
  s.addText("EcoShield Delhi", { x: M, y: 7.05, w: 5, h: 0.3, fontFace: FB, fontSize: 9, color: C.soft, charSpacing: 2 });
  s.addText(String(n).padStart(2, "0"), { x: W - M - 1, y: 7.05, w: 1, h: 0.3, fontFace: FB, fontSize: 9, color: C.soft, align: "right" });
}
function head(s, kicker, title) {
  s.addText(kicker.toUpperCase(), { x: M, y: 0.5, w: W - 2 * M, h: 0.3, fontFace: FB, fontSize: 12, bold: true, color: C.green, charSpacing: 3 });
  s.addText(title, { x: M, y: 0.82, w: W - 2 * M, h: 0.7, fontFace: FH, fontSize: 32, bold: true, color: C.ink });
}
function card(s, x, y, w, h, fill, ln) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.09, fill: { color: fill || C.card }, line: { color: ln || C.line, width: 1 }, shadow: sh() });
}
function pill(s, x, y, w, text, fill, col) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.42, rectRadius: 0.21, fill: { color: fill } });
  s.addText(text, { x, y, w, h: 0.42, fontFace: FB, fontSize: 12, bold: true, color: col, align: "center", valign: "middle", margin: 0 });
}

// ───────────────────────── 1. TITLE ─────────────────────────
let s = pres.addSlide(); s.background = { color: C.forest };
s.addShape(pres.shapes.OVAL, { x: 10.6, y: -1.4, w: 4.2, h: 4.2, fill: { color: C.green, transparency: 55 } });
s.addShape(pres.shapes.OVAL, { x: 11.7, y: 4.6, w: 3.4, h: 3.4, fill: { color: C.green, transparency: 65 } });
s.addText("AGENTIC AI   ·   AUTONOMOUS LOGISTICS   ·   URBAN AIR QUALITY",
  { x: M, y: 1.55, w: 11, h: 0.4, fontFace: FB, fontSize: 13, bold: true, color: C.mint, charSpacing: 3 });
s.addText("EcoShield Delhi", { x: M, y: 2.05, w: 11.5, h: 1.2, fontFace: FH, fontSize: 56, bold: true, color: "FFFFFF" });
s.addText("Agentic AI Pollution-Control System", { x: M, y: 3.35, w: 11.5, h: 0.7, fontFace: FH, fontSize: 28, color: C.mint2 });
s.addText("A decentralised fleet of anti-smog water-sprinkler tankers and dedicated road-cleaning trucks, routed across the Delhi Metro network by a central AI coordinator running a modified multi-objective Dijkstra solver.",
  { x: M, y: 4.25, w: 9.6, h: 1.1, fontFace: FB, fontSize: 17, color: "C9DCD3", lineSpacingMultiple: 1.15 });
pill(s, M, 5.85, 1.7, "krishiv47", C.green, C.mint2);
pill(s, M + 1.85, 5.85, 4.6, "krishiv47.github.io/ecoshield-delhi-ai", "0C3A2B", C.mint2);
pill(s, M + 6.6, 5.85, 4.4, "github.com/krishiv47/ecoshield-delhi-ai", "0C3A2B", "C3C0FF");

// ───────────────────────── 2. PROBLEM ─────────────────────────
s = pres.addSlide(); s.background = { color: C.bg };
head(s, "The problem", "Delhi's air is a moving, time-critical target");
s.addText("PM2.5 hotspots flare unpredictably with traffic surges, industrial haze, inversions and road & construction dust resuspended by passing traffic. Static smog towers cannot follow the pollution — mitigation has to be mobile, predictive and coordinated.",
  { x: M, y: 1.75, w: 11.9, h: 1.0, fontFace: FB, fontSize: 18, color: C.muted, lineSpacingMultiple: 1.15 });
const stats2 = [["250+", "PM2.5 (ug/m3) marks a severe hotspot", C.error], ["Road dust", "A leading PM source, kicked up by traffic", C.amber], ["Minutes", "The window to act before a spike worsens", C.indigo]];
stats2.forEach((d, i) => {
  const x = M + i * 4.07; card(s, x, 3.05, 3.77, 2.0, C.card, C.line);
  s.addText(d[0], { x: x + 0.3, y: 3.3, w: 3.2, h: 0.9, fontFace: FH, fontSize: 40, bold: true, color: d[2] });
  s.addText(d[1], { x: x + 0.3, y: 4.25, w: 3.2, h: 0.7, fontFace: FB, fontSize: 14, color: C.muted });
});
s.addText([{ text: "Goal:  ", options: { bold: true, color: C.green } }, { text: "mitigate hotspots before sensors confirm them, coordinate many trucks as one fleet, and keep every unit fuelled, watered and optimally routed — autonomously.", options: { color: C.muted } }],
  { x: M, y: 5.5, w: 11.9, h: 0.8, fontFace: FB, fontSize: 17 });
footer(s, 2);

// ───────────────────────── 3. SOLUTION ─────────────────────────
s = pres.addSlide(); s.background = { color: C.bg };
head(s, "The solution", "One brain, two coordinated fleets");
const sol = [
  ["Central AI Coordinator", "Global telemetry of the network and fleet. Predicts spikes, dispatches sub-fleets, handles exceptions and enforces the supply lifecycle.", C.green],
  ["Two truck fleets", "16 anti-smog water-sprinkler tankers that mist hotspots, plus 10 dedicated road-cleaning trucks that wash roads and suppress dust.", C.green],
  ["Delhi Metro network", "~50 real stations across all lines plus 6 water / charging depots form the directed road graph the fleet operates on.", C.green],
];
sol.forEach((d, i) => {
  const x = M + i * 4.07; card(s, x, 1.85, 3.77, 2.4, C.card, C.line);
  s.addText(d[0], { x: x + 0.3, y: 2.1, w: 3.2, h: 0.5, fontFace: FH, fontSize: 18, bold: true, color: d[2] });
  s.addText(d[1], { x: x + 0.3, y: 2.65, w: 3.25, h: 1.45, fontFace: FB, fontSize: 14, color: C.muted, lineSpacingMultiple: 1.1 });
});
card(s, M, 4.55, 11.93, 1.75, C.indigoLite, "C3C0FF");
s.addText("Why “agentic”", { x: M + 0.35, y: 4.75, w: 11, h: 0.4, fontFace: FH, fontSize: 17, bold: true, color: C.indigoInk });
s.addText("The system perceives (live AQI + traffic), reasons (predict, score, route) and acts (dispatch, spray, wash, replenish) in a continuous closed loop — with no human in the routing decision. Drivers are bounded actuators behind a lockable console.",
  { x: M + 0.35, y: 5.15, w: 11.3, h: 1.0, fontFace: FB, fontSize: 14.5, color: "3A3A6A", lineSpacingMultiple: 1.12 });
footer(s, 3);

// ───────────────────────── 4. ARCHITECTURE ─────────────────────────
s = pres.addSlide(); s.background = { color: C.bg };
head(s, "System architecture", "Strict OOD, clean closed-loop flow");
function abox(x, y, w, h, fill, ln, t1, t2, c1, c2) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: ln, width: 1 } });
  s.addText(t1, { x, y: y + 0.12, w, h: 0.42, fontFace: FH, fontSize: 15, bold: true, color: c1, align: "center", margin: 0 });
  if (t2) s.addText(t2, { x, y: y + 0.52, w, h: 0.34, fontFace: FB, fontSize: 11.5, color: c2, align: "center", margin: 0 });
}
const ln = (x1, y1, x2, y2) => s.addShape(pres.shapes.LINE, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color: C.soft, width: 1.5, endArrowType: "triangle" } });
abox(4.9, 1.7, 3.5, 0.95, C.green, C.green, "Central AI Coordinator", "global telemetry · decision loop", "FFFFFF", "BFEADA");
const mid = [["Predictive analytics", ">40% influx over 2 ticks"], ["Fleet dispatcher", "score matrix · ETA sync"], ["Exception handler", "stuck · supply lifecycle"]];
mid.forEach((d, i) => abox(1.4 + i * 3.7, 3.15, 3.2, 0.95, C.indigoLite, "C3C0FF", d[0], d[1], C.indigoInk, C.indigo));
const bot = [["Transit graph G=(V,E)", "stations + depots"], ["Dijkstra router", "multi-objective weights"], ["Truck fleets", "telemetry every tick"]];
bot.forEach((d, i) => abox(1.4 + i * 3.7, 4.7, 3.2, 0.95, C.card, C.line, d[0], d[1], C.ink, C.muted));
ln(5.6, 2.65, 3.0, 3.13); ln(6.65, 2.65, 6.65, 3.13); ln(7.7, 2.65, 10.3, 3.13);
ln(3.0, 4.1, 3.0, 4.68); ln(6.65, 4.1, 6.65, 4.68); ln(10.3, 4.1, 10.3, 4.68);
s.addShape(pres.shapes.LINE, { x: 10.3, y: 5.65, w: 0, h: 0.7, line: { color: C.soft, width: 1.2, dashType: "dash" } });
s.addShape(pres.shapes.LINE, { x: 6.65, y: 6.35, w: 3.65, h: 0, line: { color: C.soft, width: 1.2, dashType: "dash" } });
s.addShape(pres.shapes.LINE, { x: 6.65, y: 2.65, w: 0, h: 3.7, line: { color: C.soft, width: 1.2, dashType: "dash", endArrowType: "triangle" } });
s.addText("telemetry feeds back to the coordinator — a continuous closed loop", { x: 6.8, y: 6.05, w: 5, h: 0.3, fontFace: FB, fontSize: 11, italic: true, color: C.soft });
footer(s, 4);

// ───────────────────────── 5. DOMAIN MODEL ─────────────────────────
s = pres.addSlide(); s.background = { color: C.bg };
head(s, "Domain model", "A directed graph with live, stateful telemetry");
s.addText([
  { text: "Nodes (V): ", options: { bold: true, color: C.ink } }, { text: "metro stations carrying dynamic PM2.5 and traffic influx, with rolling history.", options: { color: C.muted, breakLine: true } },
  { text: "Special nodes: ", options: { bold: true, color: C.ink } }, { text: "Sewage Treatment Plants (recycled water) and CNG/EV depots, via an abstract base.", options: { color: C.muted, breakLine: true } },
  { text: "Edges (E): ", options: { bold: true, color: C.ink } }, { text: "stateful road segments; congestion factor and emission penalty mutate each tick.", options: { color: C.muted, breakLine: true } },
  { text: "Geometry: ", options: { bold: true, color: C.ink } }, { text: "every edge snapped to real road shapes (OSRM) so paths follow actual streets.", options: { color: C.muted } },
], { x: M, y: 1.85, w: 6.6, h: 3.6, fontFace: FB, fontSize: 16, lineSpacingMultiple: 1.35, bullet: { code: "2022", indent: 16 } });
const ds = [["50", "metro stations, all lines"], ["6", "water / charging depots"], ["134", "directed weighted edges"], ["26", "trucks: 16 sprinklers + 10 cleaners"]];
ds.forEach((d, i) => {
  const x = 7.55 + (i % 2) * 2.62, y = 1.95 + Math.floor(i / 2) * 1.55;
  card(s, x, y, 2.45, 1.35, C.card, C.line);
  s.addText(d[0], { x: x + 0.22, y: y + 0.16, w: 2.0, h: 0.58, fontFace: FH, fontSize: 28, bold: true, color: i < 2 ? C.green : C.indigo });
  s.addText(d[1], { x: x + 0.22, y: y + 0.78, w: 2.05, h: 0.5, fontFace: FB, fontSize: 11.5, color: C.muted, lineSpacingMultiple: 1.0 });
});
s.addText("Truck states:  IDLE   ·   EN_ROUTE   ·   SPRAYING   ·   STUCK   ·   REPLENISHING   ·   PATROL (road cleaners)",
  { x: M, y: 5.7, w: 11.9, h: 0.5, fontFace: FM, fontSize: 13, color: C.green, bold: true });
footer(s, 5);

// ───────────────────────── 6. MATH ─────────────────────────
s = pres.addSlide(); s.background = { color: C.bg };
head(s, "Mathematical core", "Modified multi-objective Dijkstra");
s.addText("Edge weight blends congestion-stretched travel time with a dynamic, vehicle-aware emission overhead — not static distance.",
  { x: M, y: 1.7, w: 11.9, h: 0.55, fontFace: FB, fontSize: 16, color: C.muted });
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 2.4, w: 11.93, h: 1.85, rectRadius: 0.08, fill: { color: "0F1720" } });
s.addText([
  { text: "W(e) = ( distance_km / base_speed ) x traffic_density_factor + emission_penalty", options: { color: "E6EDF3", breakLine: true } },
  { text: "emission_penalty = COEF x emission_weight(vehicle) x traffic_factor x severity", options: { color: "56D364", breakLine: true } },
  { text: "( levied only when a heavy chassis idles into an already-critical cell )", options: { color: "8B949E", italic: true } },
], { x: M + 0.4, y: 2.62, w: 11.1, h: 1.4, fontFace: FM, fontSize: 16, lineSpacingMultiple: 1.45 });
const mc = [["Vehicle-aware", "Mini / Medium / Heavy get different optimal paths over the same graph."], ["Dynamic", "Weights recomputed from live telemetry; gridlock reroutes onto open bypasses."], ["Efficient", "Binary-heap Dijkstra, O((V+E) log V), in Python and in the browser."]];
mc.forEach((d, i) => {
  const x = M + i * 4.07; card(s, x, 4.55, 3.77, 1.7, C.card, C.line);
  s.addText(d[0], { x: x + 0.3, y: 4.75, w: 3.2, h: 0.4, fontFace: FH, fontSize: 16, bold: true, color: C.indigo });
  s.addText(d[1], { x: x + 0.3, y: 5.18, w: 3.25, h: 1.0, fontFace: FB, fontSize: 13, color: C.muted, lineSpacingMultiple: 1.1 });
});
footer(s, 6);

// ───────────────────────── 7. WORKFLOW ─────────────────────────
s = pres.addSlide(); s.background = { color: C.bg };
head(s, "Agentic workflow", "The closed loop, every tick");
const steps = [
  ["1", "Sense", "Ingest live PM2.5 and traffic from every station and road segment."],
  ["2", "Predict", "Flag a breach when traffic rises >40% over two ticks, before sensors."],
  ["3", "Dispatch", "Score matrix picks a 2-3 truck sub-fleet; arrivals are staggered."],
  ["4", "Route", "Modified Dijkstra computes each truck's vehicle-aware path."],
  ["5", "Mitigate", "Tankers mist hotspots; road cleaners wash streets and bind dust."],
  ["6", "Adapt", "Handle stuck trucks: mist in place, or reroute to an open unit."],
  ["7", "Replenish", "Low water/fuel locks the console and routes to the nearest depot."],
  ["8", "Repeat", "Continuously, with a resting reserve always on standby."],
];
steps.forEach((d, i) => {
  const col = Math.floor(i / 4), row = i % 4;
  const x = M + col * 6.1, y = 1.85 + row * 1.18;
  s.addShape(pres.shapes.OVAL, { x, y, w: 0.5, h: 0.5, fill: { color: i % 2 ? C.indigo : C.green } });
  s.addText(d[0], { x, y, w: 0.5, h: 0.5, fontFace: FH, fontSize: 16, bold: true, color: "FFFFFF", align: "center", valign: "middle", margin: 0 });
  s.addText(d[1], { x: x + 0.7, y: y - 0.04, w: 5.2, h: 0.4, fontFace: FH, fontSize: 16, bold: true, color: C.ink });
  s.addText(d[2], { x: x + 0.7, y: y + 0.34, w: 5.25, h: 0.7, fontFace: FB, fontSize: 12.5, color: C.muted, lineSpacingMultiple: 1.05 });
});
footer(s, 7);

// ───────────────────────── 8. ROAD CLEANING ─────────────────────────
s = pres.addSlide(); s.background = { color: C.bg };
head(s, "Road cleaning & dust suppression", "Keeping particles on the ground");
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 1.85, w: 3.3, h: 4.3, rectRadius: 0.1, fill: { color: C.teal } });
s.addText("10", { x: M, y: 2.4, w: 3.3, h: 1.4, fontFace: FH, fontSize: 96, bold: true, color: "FFFFFF", align: "center", margin: 0 });
s.addText("dedicated road-cleaning trucks", { x: M + 0.25, y: 3.9, w: 2.8, h: 0.8, fontFace: FB, fontSize: 16, bold: true, color: "EAFBF7", align: "center" });
s.addText("continuously patrolling the busiest, dustiest corridors", { x: M + 0.25, y: 4.7, w: 2.8, h: 1.0, fontFace: FB, fontSize: 13, color: "D2F1EC", align: "center", lineSpacingMultiple: 1.1 });
card(s, 4.4, 1.85, 8.23, 2.05, C.tealLite, "9FE1CB");
s.addText("What they do", { x: 4.7, y: 2.05, w: 7.6, h: 0.4, fontFace: FH, fontSize: 17, bold: true, color: C.tealInk });
s.addText("Beyond misting the air, the cleaners wet-wash the road surface — binding settled road and construction dust so it stays on the ground instead of being kicked back into the air as PM10 / PM2.5 by passing traffic.",
  { x: 4.7, y: 2.5, w: 7.65, h: 1.3, fontFace: FB, fontSize: 15, color: C.muted, lineSpacingMultiple: 1.2 });
card(s, 4.4, 4.1, 8.23, 2.05, C.card, C.line);
s.addText("Why it matters", { x: 4.7, y: 4.3, w: 7.6, h: 0.4, fontFace: FH, fontSize: 17, bold: true, color: C.green });
s.addText([
  { text: "Road dust is one of Delhi's largest PM sources; resuspension by traffic re-pollutes even cleared zones.", options: { color: C.muted, breakLine: true } },
  { text: "A dedicated cleaning fleet works the network continuously, so the air-misting tankers are freed to chase acute hotspots.", options: { color: C.muted } },
], { x: 4.7, y: 4.75, w: 7.7, h: 1.3, fontFace: FB, fontSize: 14, lineSpacingMultiple: 1.18, bullet: { code: "2022", indent: 14 } });
footer(s, 8);

// ───────────────────────── 9. EXCEPTIONS ─────────────────────────
s = pres.addSlide(); s.background = { color: C.bg };
head(s, "Exception logic", "The two “stuck in traffic” branches");
card(s, M, 1.95, 5.85, 3.7, C.coralLite, "F0997B");
pill(s, M + 0.35, 2.2, 3.3, "Inside the hotspot zone", "F5C4B3", C.coralInk);
s.addText("Stationary misting curtain", { x: M + 0.35, y: 2.85, w: 5.1, h: 0.5, fontFace: FH, fontSize: 19, bold: true, color: C.coralInk });
s.addText("A truck trapped within the target zone engages its cannons in place — a pitch-adjusted curtain knocking down the idling exhaust of the surrounding gridlock. The mission is kept.",
  { x: M + 0.35, y: 3.4, w: 5.25, h: 2.0, fontFace: FB, fontSize: 15, color: C.muted, lineSpacingMultiple: 1.2 });
card(s, 6.78, 1.95, 5.85, 3.7, C.blueLite, "85B7EB");
pill(s, 7.13, 2.2, 3.0, "Far from the hotspot", "B5D4F4", "0C447C");
s.addText("En-route interception", { x: 7.13, y: 2.85, w: 5.1, h: 0.5, fontFace: FH, fontSize: 19, bold: true, color: C.blue });
s.addText("A truck trapped mid-transit has its target revoked and console locked; it is marked STUCK, the graph is recomputed, and the workload is re-allocated to a moving unit with an open bypass.",
  { x: 7.13, y: 3.4, w: 5.25, h: 2.0, fontFace: FB, fontSize: 15, color: C.muted, lineSpacingMultiple: 1.2 });
s.addText([{ text: "Recovery:  ", options: { bold: true, color: C.green } }, { text: "stuck units rejoin the reserve once their segment clears; the displaced load is topped up by the next dispatch pass.", options: { color: C.muted } }],
  { x: M, y: 5.85, w: 11.9, h: 0.6, fontFace: FB, fontSize: 15 });
footer(s, 9);

// ───────────────────────── 10. DASHBOARD ─────────────────────────
s = pres.addSlide(); s.background = { color: C.bg };
head(s, "Operations console", "A live, data-driven dashboard");
s.addText("Built on a Material-style design system (no emojis), rendered over a real Leaflet map of Delhi. Five working views, one continuously-running simulation.",
  { x: M, y: 1.7, w: 11.9, h: 0.55, fontFace: FB, fontSize: 16, color: C.muted });
const views = [["Admin Control", "Live map, hotspots, fleet, event stream"], ["Fleet Ops", "Roster of every truck; open a driver console"], ["Metro Network", "Station air quality across all lines"], ["Routing Engine", "Interactive Dijkstra path finder"], ["System Health", "Platform & coordinator telemetry"]];
views.forEach((d, i) => {
  const x = M + i * 2.42; card(s, x, 2.5, 2.25, 1.95, C.card, C.line);
  s.addShape(pres.shapes.RECTANGLE, { x: x, y: 2.5, w: 2.25, h: 0.12, fill: { color: i < 3 ? C.green : C.indigo } });
  s.addText(d[0], { x: x + 0.2, y: 2.78, w: 1.9, h: 0.7, fontFace: FH, fontSize: 15, bold: true, color: i < 3 ? C.green : C.indigo });
  s.addText(d[1], { x: x + 0.2, y: 3.45, w: 1.9, h: 0.9, fontFace: FB, fontSize: 12, color: C.muted, lineSpacingMultiple: 1.08 });
});
s.addText("Tankers shown filled = misting, hollow = resting; road cleaners as teal squares; metro lines in their official colours; gridlock highlighted live.",
  { x: M, y: 4.8, w: 11.9, h: 0.8, fontFace: FB, fontSize: 15, color: C.muted, lineSpacingMultiple: 1.15 });
footer(s, 10);

// ───────────────────────── 11. DRIVER / ROLES ─────────────────────────
s = pres.addSlide(); s.background = { color: C.bg };
head(s, "Role-based access", "The human steers, the AI dictates");
s.addText([
  { text: "A restricted in-cab Driver Console shows the assigned mission, the Dijkstra route and water / charge gauges.", options: { color: C.muted, breakLine: true } },
  { text: "Admin modules are locked for drivers — bounded actuator only.", options: { color: C.muted, breakLine: true } },
  { text: "The admin can open any driver's console (one-way hierarchy).", options: { color: C.muted, breakLine: true } },
  { text: "A “console locked” banner appears whenever the AI overrides the route.", options: { color: C.muted } },
], { x: M, y: 1.95, w: 6.3, h: 3.6, fontFace: FB, fontSize: 16, lineSpacingMultiple: 1.35, bullet: { code: "2022", indent: 16 } });
abox(7.4, 2.2, 2.4, 1.0, C.green, C.green, "Admin", "Fleet Commander", "FFFFFF", "BFEADA");
abox(10.2, 2.2, 2.4, 1.0, C.card, C.line, "Driver", "in-cab console", C.ink, C.muted);
s.addShape(pres.shapes.LINE, { x: 9.8, y: 2.55, w: 0.4, h: 0, line: { color: C.green, width: 2.5, endArrowType: "triangle" } });
s.addText("can open", { x: 9.55, y: 2.62, w: 0.95, h: 0.3, fontFace: FB, fontSize: 10, bold: true, color: C.green, align: "center" });
s.addShape(pres.shapes.LINE, { x: 10.2, y: 2.95, w: 0.4, h: 0, line: { color: C.error, width: 2.5, dashType: "dash" } });
s.addText("blocked", { x: 9.55, y: 2.96, w: 0.95, h: 0.3, fontFace: FB, fontSize: 10, bold: true, color: C.error, align: "center" });
card(s, 7.4, 3.55, 5.23, 2.0, C.errLite, "F09595");
s.addText("Locked for drivers", { x: 7.7, y: 3.75, w: 4.7, h: 0.4, fontFace: FH, fontSize: 15, bold: true, color: C.errInk });
s.addText("Admin Control · Fleet Ops · Metro Network · Routing Engine · System Health",
  { x: 7.7, y: 4.2, w: 4.7, h: 1.2, fontFace: FB, fontSize: 13.5, color: "A32D2D", lineSpacingMultiple: 1.2 });
footer(s, 11);

// ───────────────────────── 12. TECH & DEPLOY ─────────────────────────
s = pres.addSlide(); s.background = { color: C.bg };
head(s, "Engineering & deployment", "Production-grade, fully reproducible");
const tech = [["Core engine", "Python 3.10+, standard library only. Strict OOD: dataclasses, enums, ABCs, type hints, binary-heap Dijkstra."], ["Front end", "Tailwind + Inter design system, Leaflet on OpenStreetMap / CARTO. No build step; Mappls-ready via one key."], ["Delivery", "Public GitHub repo, GitHub Pages deploy, continuously-running build, 28 passing tests."]];
tech.forEach((d, i) => {
  const x = M + i * 4.07; card(s, x, 1.9, 3.77, 2.3, C.card, C.line);
  s.addText(d[0], { x: x + 0.3, y: 2.12, w: 3.2, h: 0.45, fontFace: FH, fontSize: 17, bold: true, color: C.green });
  s.addText(d[1], { x: x + 0.3, y: 2.62, w: 3.25, h: 1.5, fontFace: FB, fontSize: 13.5, color: C.muted, lineSpacingMultiple: 1.12 });
});
const td = [["28", "tests passing", C.green], ["0", "runtime dependencies", C.green], ["Live", "on GitHub Pages", C.indigo]];
td.forEach((d, i) => {
  const x = M + i * 4.07; card(s, x, 4.45, 3.77, 1.75, C.bg, C.line);
  s.addText(d[0], { x: x + 0.3, y: 4.62, w: 3.2, h: 0.7, fontFace: FH, fontSize: 34, bold: true, color: d[2] });
  s.addText(d[1], { x: x + 0.3, y: 5.42, w: 3.2, h: 0.5, fontFace: FB, fontSize: 13, color: C.muted });
});
footer(s, 12);

// ───────────────────────── 13. CLOSING ─────────────────────────
s = pres.addSlide(); s.background = { color: C.forest };
s.addShape(pres.shapes.OVAL, { x: -1.4, y: 4.5, w: 4.4, h: 4.4, fill: { color: C.green, transparency: 60 } });
s.addText("THANK YOU", { x: M, y: 1.7, w: 11, h: 0.4, fontFace: FB, fontSize: 13, bold: true, color: C.mint, charSpacing: 4 });
s.addText("An autonomous shield for Delhi's air", { x: M, y: 2.2, w: 11.5, h: 1.6, fontFace: FH, fontSize: 46, bold: true, color: "FFFFFF", lineSpacingMultiple: 1.05 });
s.addText("Perceive, predict, dispatch, mitigate — continuously, and without a human in the routing loop.",
  { x: M, y: 3.95, w: 10, h: 0.8, fontFace: FB, fontSize: 18, color: "C9DCD3" });
pill(s, M, 5.4, 5.0, "Live  ·  krishiv47.github.io/ecoshield-delhi-ai", "0C3A2B", C.mint2);
pill(s, M + 5.2, 5.4, 4.8, "Source  ·  github.com/krishiv47/ecoshield-delhi-ai", "0C3A2B", "C3C0FF");

pres.writeFile({ fileName: "EcoShield-Delhi.pptx" }).then(f => console.log("wrote " + f));
