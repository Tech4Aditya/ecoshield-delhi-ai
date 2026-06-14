#!/usr/bin/env python3
"""
Generate a standalone, animated HTML visualisation of the simulation.

    python3 visualize.py                 # -> writes simulation.html (16 ticks)
    python3 visualize.py --ticks 24 --seed 42 --open

Open the resulting ``simulation.html`` in any browser (double-click it, or pass
``--open`` to launch it automatically). No web server or dependencies needed:
the simulation data is embedded directly in the file.

The page renders Delhi's transit graph as an animated map -- junctions
colour-coded by live PM2.5, anti-smog tankers moving along the roads, gridlocked
segments highlighted, plus a scrubbable timeline, the AI event log and live
fleet/mission stats.
"""

from __future__ import annotations

import argparse
import json
import os
import webbrowser

from smog_control import SimulationEngine

# --------------------------------------------------------------------------- #
# HTML template (literal braces; data injected at the __DATA__ token)         #
# --------------------------------------------------------------------------- #
_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Agentic AI Pollution-Control — Delhi Anti-Smog Tanker Network</title>
<style>
  :root{ --bg:#0d1117; --panel:#161b22; --edge:#30363d; --ink:#e6edf3; --dim:#8b949e; }
  *{ box-sizing:border-box; }
  body{ margin:0; background:var(--bg); color:var(--ink);
        font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  header{ padding:14px 20px; border-bottom:1px solid var(--edge); }
  header h1{ font-size:17px; margin:0; font-weight:650; }
  header p{ margin:3px 0 0; color:var(--dim); font-size:12px; }
  .wrap{ display:flex; gap:14px; padding:14px; align-items:flex-start; flex-wrap:wrap; }
  .mapcard{ background:var(--panel); border:1px solid var(--edge); border-radius:12px;
            padding:10px; flex:1 1 640px; min-width:340px; }
  svg{ width:100%; height:auto; display:block; }
  .side{ width:340px; flex:1 1 300px; display:flex; flex-direction:column; gap:14px; }
  .card{ background:var(--panel); border:1px solid var(--edge); border-radius:12px; padding:12px 14px; }
  .card h2{ font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--dim);
            margin:0 0 8px; }
  .stats{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .stat{ background:#0d1117; border:1px solid var(--edge); border-radius:8px; padding:8px 10px; }
  .stat .v{ font-size:20px; font-weight:700; }
  .stat .k{ font-size:11px; color:var(--dim); }
  .controls{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:6px; }
  button{ background:#21262d; color:var(--ink); border:1px solid var(--edge); border-radius:7px;
          padding:6px 11px; font-size:13px; cursor:pointer; }
  button:hover{ background:#30363d; }
  input[type=range]{ flex:1; min-width:120px; }
  #log{ height:230px; overflow-y:auto; font-size:12px; line-height:1.5;
        font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
  #log div{ padding:2px 0; border-bottom:1px solid #1f242c; white-space:pre-wrap; }
  .t-exc{ color:#ff7b72; } .t-pred{ color:#f0b72f; } .t-disp{ color:#79c0ff; }
  .t-clr{ color:#56d364; } .t-sup{ color:#ffa657; } .t-dim{ color:#8b949e; }
  .legend{ font-size:11.5px; color:var(--dim); line-height:1.9; }
  .legend span{ display:inline-block; width:11px; height:11px; border-radius:3px;
                margin-right:5px; vertical-align:-1px; }
  .truckrow{ display:flex; justify-content:space-between; font-size:11.5px; padding:2px 0;
             font-family:ui-monospace,Menlo,monospace; border-bottom:1px solid #1f242c;}
  .pill{ font-size:10px; padding:1px 6px; border-radius:10px; }
  text{ font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif; }
  .nodelabel{ font-size:9.5px; fill:var(--ink); }
  .aqilabel{ font-size:9px; font-weight:700; }
  .trucklabel{ font-size:8px; font-weight:700; fill:#fff; }
  .pulse{ animation:pulse 1.1s ease-in-out infinite; }
  @keyframes pulse{ 0%,100%{ opacity:.25 } 50%{ opacity:.9 } }
  .tgroup{ transition:transform .55s linear; }
</style>
</head>
<body>
<header>
  <h1>🚛 Agentic AI Pollution-Control System — Delhi Anti-Smog Tanker Network</h1>
  <p>Central AI Coordinator · Modified Multi-Objective Dijkstra · live PM2.5 mitigation</p>
</header>
<div class="wrap">
  <div class="mapcard">
    <svg id="map" viewBox="0 0 760 560" preserveAspectRatio="xMidYMid meet"></svg>
  </div>
  <div class="side">
    <div class="card">
      <h2 id="tickhdr">Tick</h2>
      <div class="stats">
        <div class="stat"><div class="v" id="s-aqi">–</div><div class="k">mean junction PM2.5</div></div>
        <div class="stat"><div class="v" id="s-act">–</div><div class="k">active missions</div></div>
        <div class="stat"><div class="v" id="s-res">–</div><div class="k">resolved</div></div>
        <div class="stat"><div class="v" id="s-bil">–</div><div class="k">fast-pass INR</div></div>
      </div>
      <div class="controls">
        <button id="play">▶ Play</button>
        <button id="prev">◀</button>
        <button id="next">▶</button>
        <input type="range" id="scrub" min="0" value="0"/>
        <select id="speed">
          <option value="1400">0.7×</option>
          <option value="950" selected>1×</option>
          <option value="500">2×</option>
          <option value="250">4×</option>
        </select>
      </div>
    </div>
    <div class="card">
      <h2>AI Coordinator Event Log</h2>
      <div id="log"></div>
    </div>
    <div class="card">
      <h2>Fleet</h2>
      <div id="fleet"></div>
    </div>
    <div class="card">
      <h2>Legend</h2>
      <div class="legend">
        <span style="background:#2ecc71"></span>Good
        <span style="background:#f1c40f"></span>Moderate
        <span style="background:#e67e22"></span>Poor
        <span style="background:#e74c3c"></span>Very&nbsp;Poor
        <span style="background:#8e44ad"></span>Severe<br/>
        <span style="background:#79c0ff"></span>En-route
        <span style="background:#56d364"></span>Spraying
        <span style="background:#ff7b72"></span>Stuck
        <span style="background:#ffa657"></span>Replenish
        <span style="background:#8b949e"></span>Idle &nbsp;|&nbsp; ◆ STP / CNG &nbsp; ⬤ junction
      </div>
    </div>
  </div>
</div>
<script>
const SIM = __DATA__;
const meta = SIM.meta, frames = SIM.frames;
const W = 760, H = 560, PAD = 46;
const b = meta.bounds;
const sx = v => PAD + (v - b.minx) / (b.maxx - b.minx) * (W - 2*PAD);
const sy = v => (H - 70) - (v - b.miny) / (b.maxy - b.miny) * ((H - 70) - PAD);  // flip Y

const NS = "http://www.w3.org/2000/svg";
const svg = document.getElementById("map");
function el(tag, attrs){ const e = document.createElementNS(NS, tag);
  for(const k in attrs) e.setAttribute(k, attrs[k]); return e; }

function aqiColor(aqi){
  if(aqi < 60) return "#2ecc71";
  if(aqi < 90) return "#a9d86e";
  if(aqi < 120) return "#f1c40f";
  if(aqi < 200) return "#e67e22";
  if(aqi < 250) return "#e74c3c";
  return "#8e44ad";
}
const STATUS = { IDLE:"#8b949e", EN_ROUTE:"#79c0ff", SPRAYING:"#56d364",
                 STUCK:"#ff7b72", REPLENISHING:"#ffa657" };

// ---- static layer: links + nodes ----
const nodePos = {};
meta.nodes.forEach(n => nodePos[n.id] = {x:sx(n.x), y:sy(n.y), name:n.name, type:n.type, r:n.radius_km});
const linkLayer = el("g",{}), congLayer = el("g",{}), nodeLayer = el("g",{}), truckLayer = el("g",{});
svg.append(linkLayer, congLayer, nodeLayer, truckLayer);

meta.links.forEach(l => {
  const a = nodePos[l.s], c = nodePos[l.t];
  linkLayer.append(el("line",{x1:a.x,y1:a.y,x2:c.x,y2:c.y,stroke:"#30363d","stroke-width":2}));
});

const nodeEls = {};
meta.nodes.forEach(n => {
  const p = nodePos[n.id];
  const g = el("g",{});
  const ring = el(n.type==="JUNCTION"?"circle":"rect", n.type==="JUNCTION"
     ? {cx:p.x, cy:p.y, r:0} : {x:p.x, y:p.y, width:0, height:0});
  ring.setAttribute("class","pulse"); ring.setAttribute("fill","none");
  g.append(ring);
  let shape;
  if(n.type==="JUNCTION"){
    shape = el("circle",{cx:p.x, cy:p.y, r:15, stroke:"#0d1117","stroke-width":2});
  } else {
    shape = el("rect",{x:p.x-12, y:p.y-12, width:24, height:24, rx:5,
                       transform:`rotate(45 ${p.x} ${p.y})`,
                       fill:"#1f6feb", stroke:"#0d1117","stroke-width":2});
  }
  g.append(shape);
  const lab = el("text",{x:p.x, y:p.y-20, "text-anchor":"middle"}); lab.setAttribute("class","nodelabel");
  lab.textContent = p.name + (n.type!=="JUNCTION" ? " ("+n.type+")" : "");
  const aqit = el("text",{x:p.x, y:p.y+4, "text-anchor":"middle"}); aqit.setAttribute("class","aqilabel");
  nodeLayer.append(g); g.append(lab); g.append(aqit);
  nodeEls[n.id] = {shape, aqit, ring, type:n.type, p};
});

// ---- dynamic truck markers ----
const truckEls = {};
meta.fleet.forEach(t => {
  const g = el("g",{}); g.setAttribute("class","tgroup");
  const c = el("circle",{r:8, stroke:"#0d1117","stroke-width":1.5, fill:"#8b949e"});
  const lab = el("text",{"text-anchor":"middle", y:3}); lab.setAttribute("class","trucklabel");
  lab.textContent = t.id;
  g.append(c, lab); truckLayer.append(g);
  truckEls[t.id] = {g, c};
});

function tagClass(line){
  if(line.includes("EXCEPTION")||line.includes("STUCK")) return "t-exc";
  if(line.includes("PREDICT")) return "t-pred";
  if(line.includes("DISPATCH")||line.includes("TOP-UP")) return "t-disp";
  if(line.includes("MISSION CLR")||line.includes("ON-SITE")||line.includes("RECOVERED")) return "t-clr";
  if(line.includes("SUPPLY")||line.includes("FASTPASS")||line.includes("REPLENISH")) return "t-sup";
  return "t-dim";
}

const scrub = document.getElementById("scrub");
scrub.max = frames.length - 1;

function render(i){
  const f = frames[i];
  const aqiById = {}; f.nodes.forEach(n => aqiById[n.id]=n);
  // nodes
  f.nodes.forEach(n => {
    const e = nodeEls[n.id]; if(!e) return;
    e.aqit.textContent = n.aqi;
    if(e.type==="JUNCTION"){ e.shape.setAttribute("fill", aqiColor(n.aqi)); }
    e.aqit.setAttribute("fill", n.aqi>=120 ? "#fff" : "#111");
    // hotspot / predictive rings
    if(n.hotspot){ e.ring.setAttribute("stroke","#ff3b30"); e.ring.setAttribute("stroke-width",4);
      if(e.type==="JUNCTION") e.ring.setAttribute("r",23); }
    else if(n.predictive){ e.ring.setAttribute("stroke","#f0b72f"); e.ring.setAttribute("stroke-width",3);
      e.ring.setAttribute("stroke-dasharray","4 3"); if(e.type==="JUNCTION") e.ring.setAttribute("r",22); }
    else { e.ring.setAttribute("stroke","none"); if(e.type==="JUNCTION") e.ring.setAttribute("r",0); }
  });
  // congested edges overlay
  congLayer.innerHTML = "";
  f.congested.forEach(c => {
    const a = nodePos[c.s], d = nodePos[c.t]; if(!a||!d) return;
    const grid = c.factor >= 6;
    congLayer.append(el("line",{x1:a.x,y1:a.y,x2:d.x,y2:d.y,
      stroke: grid? "#ff3b30":"#ffa657", "stroke-width": grid?5:3,
      "stroke-dasharray": grid? "2 4":"6 4", opacity:.85}));
  });
  // trucks
  f.trucks.forEach(t => {
    const e = truckEls[t.id]; if(!e) return;
    e.g.setAttribute("transform", `translate(${sx(t.x)},${sy(t.y)})`);
    e.c.setAttribute("fill", STATUS[t.status] || "#8b949e");
    e.c.setAttribute("class", t.stationary ? "pulse" : "");
    e.c.setAttribute("r", t.class==="HEAVY"?9 : t.class==="MEDIUM"?8 : 7);
  });
  // stats
  const js = f.nodes.filter(n => !["STP","REFUELING"].includes(meta.nodes.find(m=>m.id===n.id).type));
  const mean = Math.round(js.reduce((a,n)=>a+n.aqi,0)/js.length);
  document.getElementById("s-aqi").textContent = mean;
  document.getElementById("s-act").textContent = f.missions_active;
  document.getElementById("s-res").textContent = f.missions_resolved;
  document.getElementById("s-bil").textContent = f.billed;
  document.getElementById("tickhdr").textContent = `Tick ${f.tick}  ·  T+${f.minute} min`;
  // event log
  const log = document.getElementById("log"); log.innerHTML = "";
  if(f.events.length===0){ const d=document.createElement("div"); d.className="t-dim";
    d.textContent="(no coordinator actions this tick)"; log.append(d); }
  f.events.forEach(line => { const d=document.createElement("div"); d.className=tagClass(line);
    d.textContent=line; log.append(d); });
  // fleet panel
  const fl = document.getElementById("fleet"); fl.innerHTML="";
  f.trucks.forEach(t => { const d=document.createElement("div"); d.className="truckrow";
    d.innerHTML = `<span><b>${t.id}</b> ${t.class}</span>`
      + `<span class="pill" style="background:${STATUS[t.status]||'#555'};color:#0d1117">${t.status}</span>`
      + `<span>💧${t.water}% ⛽${t.fuel}%</span>`; fl.append(d); });
  scrub.value = i;
}

// ---- playback ----
let i = 0, playing = false, timer = null;
function step(){ i = (i+1) % frames.length; render(i); if(i===frames.length-1) stop(); }
function play(){ playing=true; document.getElementById("play").textContent="⏸ Pause";
  const ms = +document.getElementById("speed").value; timer=setInterval(step, ms); }
function stop(){ playing=false; document.getElementById("play").textContent="▶ Play";
  clearInterval(timer); }
document.getElementById("play").onclick = ()=>{ if(playing) stop();
  else { if(i>=frames.length-1) i=0; play(); } };
document.getElementById("next").onclick = ()=>{ stop(); i=Math.min(frames.length-1,i+1); render(i); };
document.getElementById("prev").onclick = ()=>{ stop(); i=Math.max(0,i-1); render(i); };
document.getElementById("speed").onchange = ()=>{ if(playing){ stop(); play(); } };
scrub.oninput = ()=>{ stop(); i=+scrub.value; render(i); };
render(0);
</script>
</body>
</html>
"""


def build_html(ticks: int, seed: int) -> str:
    """Run the simulation and return a self-contained HTML document string."""
    engine = SimulationEngine(seed=seed, verbose=False)
    engine.run_ticks(ticks)
    payload = {"meta": engine.viz_meta(), "frames": engine.frames}
    return _TEMPLATE.replace("__DATA__", json.dumps(payload))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the HTML visualiser.")
    parser.add_argument("--ticks", type=int, default=16)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default="simulation.html")
    parser.add_argument("--open", action="store_true", help="open the file in a browser")
    args = parser.parse_args()

    html = build_html(args.ticks, args.seed)
    out_path = os.path.abspath(args.out)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Wrote {out_path}  ({len(html)//1024} KB, {args.ticks} ticks)")
    print("Open it in your browser:")
    print(f"  open '{out_path}'")
    if args.open:
        webbrowser.open("file://" + out_path)


if __name__ == "__main__":
    main()
