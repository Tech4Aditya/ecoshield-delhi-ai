#!/usr/bin/env python3
"""
Generate the EcoShield in-cab Driver Console (driver.html).

A deliberately *restricted* role view: the driver is a bounded actuator. The
administrative modules (Admin Control, Fleet Operations, Metro Network, Routing
Engine, System Health) are visible but LOCKED -- the Central AI dictates the
route and the in-cab console cannot override it.

The console follows one tanker through the continuous simulation and shows the
AI-assigned, Dijkstra-optimised route over the real Delhi Metro map, the current
mission, water/fuel gauges and the live AI instruction feed.

    python3 driver.py --open
    python3 driver.py --truck WT-13 --ticks 40 --open
"""

from __future__ import annotations

import argparse
import json
import os
import webbrowser
from collections import Counter

from smog_control import SimulationEngine
from dashboard import CORE_LATLNG


def pick_busiest_truck(frames: list[dict]) -> str:
    """Choose the tanker that spends the most ticks actively cleaning/moving."""
    active = Counter()
    for f in frames:
        for t in f["trucks"]:
            if t["status"] in ("EN_ROUTE", "SPRAYING", "REPLENISHING"):
                active[t["id"]] += 1
    return active.most_common(1)[0][0] if active else frames[0]["trucks"][0]["id"]


def _truck_frames(engine: SimulationEngine, truck_id: str) -> list[dict]:
    """Per-frame projection for one truck (status, route, gauges, target AQI, feed)."""
    seq = []
    for f in engine.frames:
        t = next((tr for tr in f["trucks"] if tr["id"] == truck_id), None)
        if t is None:
            continue
        taqi = None
        if t["target"]:
            n = next((nn for nn in f["nodes"] if nn["id"] == t["target"]), None)
            taqi = n["aqi"] if n else None
        evs = [e for e in f["events"] if truck_id in e]
        seq.append({"tick": f["tick"], "min": f["minute"], "t": t, "taqi": taqi, "ev": evs})
    return seq


def build_payload(engine: SimulationEngine, default_truck: str) -> dict:
    """Driver-centric projection for EVERY truck, selectable via ``?truck=`` URL param.

    Embedding all units lets the admin console deep-link to any driver's portal
    (admin can access the driver portal; drivers still cannot access admin modules).
    """
    meta = engine.viz_meta()
    name_by_id = {n["id"]: n["name"] for n in meta["nodes"]}
    ids = [t.truck_id for t in engine.fleet]
    trucks = {tid: _truck_frames(engine, tid) for tid in ids}
    return {"meta": meta, "names": name_by_id, "latlng": CORE_LATLNG,
            "trucks": trucks, "ids": ids, "default": default_truck}


_TEMPLATE = r"""<!DOCTYPE html>
<html class="light" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>EcoShield | In-Cab Driver Console</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@100..900&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap" rel="stylesheet"/>
<link href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css" rel="stylesheet"/>
<script>
  tailwind.config = { darkMode:"class", theme:{ extend:{
    colors:{ "primary":"#006948","on-primary":"#ffffff","primary-container":"#00855d","on-primary-container":"#f5fff7",
      "secondary":"#4b41e1","on-secondary":"#ffffff","secondary-container":"#645efb","on-secondary-container":"#fffbff",
      "tertiary":"#545c72","error":"#ba1a1a","on-error":"#ffffff","error-container":"#ffdad6","on-error-container":"#93000a",
      "background":"#f7f9fb","surface":"#f7f9fb","on-surface":"#191c1e","on-surface-variant":"#3d4a42",
      "surface-container-lowest":"#ffffff","surface-container-low":"#f2f4f6","surface-container":"#eceef0",
      "surface-container-high":"#e6e8ea","surface-container-highest":"#e0e3e5","outline":"#6d7a72","outline-variant":"#bccac0" },
    borderRadius:{ "DEFAULT":"0.25rem","lg":"0.5rem","xl":"0.75rem","2xl":"1rem","full":"9999px" },
    spacing:{ "xs":"0.5rem","sm":"1rem","md":"1.5rem","lg":"2rem","xl":"3rem","margin-desktop":"2.5rem" },
    fontFamily:{ "sans":["Inter","sans-serif"] },
    fontSize:{ "display-lg":["48px",{"lineHeight":"56px","letterSpacing":"-0.02em","fontWeight":"700"}],
      "headline-lg":["32px",{"lineHeight":"40px","letterSpacing":"-0.01em","fontWeight":"600"}],
      "title-md":["20px",{"lineHeight":"28px","fontWeight":"600"}],"body-md":["16px",{"lineHeight":"24px"}],
      "label-md":["14px",{"lineHeight":"20px","letterSpacing":"0.01em","fontWeight":"500"}],
      "label-sm":["12px",{"lineHeight":"16px","letterSpacing":"0.03em","fontWeight":"600"}] } } } };
</script>
<style>
  body{ font-family:Inter,sans-serif; }
  .material-symbols-outlined{ font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 24; }
  #map{ height:100%; width:100%; background:#e8edf0; z-index:0; }
  .leaflet-container{ font-family:Inter,sans-serif; }
  .leaflet-marker-icon.tk{ transition:transform .6s linear; background:transparent; border:none; }
  .tkdot{ width:30px;height:30px;border-radius:9999px;border:3px solid #fff;background:#006948;color:#fff;
          font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(0,0,0,.4); }
  .pulse{ animation:pulse 1.2s ease-in-out infinite; } @keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(0,105,72,.5)}50%{box-shadow:0 0 0 10px rgba(0,105,72,0)}}
  .locked{ opacity:.5; cursor:not-allowed; }
  #toast{ transition:opacity .3s; }
  .ev{ animation:fadein .4s ease; } @keyframes fadein{from{opacity:0}to{opacity:1}}
</style>
</head>
<body class="bg-background text-on-surface">
<div class="max-w-6xl mx-auto p-margin-desktop flex flex-col gap-md">

  <header class="flex flex-wrap justify-between items-center gap-3">
    <div class="flex items-center gap-3">
      <span class="material-symbols-outlined text-primary text-3xl">local_shipping</span>
      <div><h1 class="text-title-md text-primary">EcoShield Driver Console</h1>
        <p class="text-label-sm text-on-surface-variant">In-cab terminal &middot; bounded actuator mode</p></div>
    </div>
    <div class="flex items-center gap-3">
      <span class="px-3 py-1 rounded-full bg-amber-100 text-amber-800 text-label-sm font-bold flex items-center gap-1">
        <span class="material-symbols-outlined text-sm">lock</span>Driver role &middot; restricted</span>
      <div class="w-10 h-10 rounded-full bg-primary-container flex items-center justify-center text-on-primary-container font-bold" id="drv-initials">DR</div>
    </div>
  </header>

  <div class="bg-white rounded-2xl border border-outline-variant p-2 flex flex-wrap gap-2 items-center">
    <span class="text-label-sm text-on-surface-variant px-2 flex items-center gap-1"><span class="material-symbols-outlined text-sm">block</span>Locked for drivers:</span>
    <button class="locked nav-lock flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-container text-on-surface-variant text-label-md"><span class="material-symbols-outlined text-sm">dashboard</span>Admin Control<span class="material-symbols-outlined text-sm">lock</span></button>
    <button class="locked nav-lock flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-container text-on-surface-variant text-label-md"><span class="material-symbols-outlined text-sm">local_shipping</span>Fleet Operations<span class="material-symbols-outlined text-sm">lock</span></button>
    <button class="locked nav-lock flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-container text-on-surface-variant text-label-md"><span class="material-symbols-outlined text-sm">subway</span>Metro Network<span class="material-symbols-outlined text-sm">lock</span></button>
    <button class="locked nav-lock flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-container text-on-surface-variant text-label-md"><span class="material-symbols-outlined text-sm">route</span>Routing Engine<span class="material-symbols-outlined text-sm">lock</span></button>
    <button class="locked nav-lock flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-container text-on-surface-variant text-label-md"><span class="material-symbols-outlined text-sm">settings_input_component</span>System Health<span class="material-symbols-outlined text-sm">lock</span></button>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-5 gap-md">
    <div class="lg:col-span-2 flex flex-col gap-md">
      <div class="bg-white rounded-2xl border border-outline-variant shadow-sm p-6" id="status-card">
        <div class="flex justify-between items-center">
          <div><p class="text-label-sm text-on-surface-variant uppercase tracking-wider">Unit</p>
            <h2 class="text-headline-lg" id="truck-id">WT-00</h2>
            <p class="text-label-md text-on-surface-variant" id="truck-class">Heavy tanker</p></div>
          <div class="text-right"><span id="status-pill" class="px-4 py-2 rounded-full text-label-md font-bold">--</span>
            <p class="text-label-sm text-on-surface-variant mt-2" id="loc">at --</p></div>
        </div>
        <div id="lock-banner" class="mt-4 hidden bg-error-container text-on-error-container p-3 rounded-lg text-label-sm font-bold flex items-center gap-2">
          <span class="material-symbols-outlined text-sm">lock</span><span id="lock-text">Console locked by Central AI.</span></div>
      </div>

      <div class="bg-white rounded-2xl border border-outline-variant shadow-sm p-6">
        <div class="flex justify-between items-center mb-3">
          <h3 class="text-title-md flex items-center gap-2"><span class="material-symbols-outlined text-secondary">route</span>Assigned route</h3>
          <span class="px-2 py-1 rounded-full bg-secondary-container text-on-secondary-container text-label-sm font-bold">Dijkstra</span>
        </div>
        <div id="mission" class="mb-3 p-3 rounded-lg bg-surface-container-low text-label-md"></div>
        <ol id="route-list" class="space-y-1 max-h-56 overflow-y-auto pr-1"></ol>
      </div>

      <div class="grid grid-cols-2 gap-md">
        <div class="bg-white rounded-2xl border border-outline-variant shadow-sm p-5">
          <div class="flex items-center gap-2 text-label-md text-on-surface-variant"><span class="material-symbols-outlined text-primary">water_drop</span>Water</div>
          <p class="text-display-lg" id="water">0%</p>
          <div class="h-2 rounded-full bg-surface-container-high overflow-hidden"><div id="water-bar" class="h-full bg-primary" style="width:0%"></div></div>
        </div>
        <div class="bg-white rounded-2xl border border-outline-variant shadow-sm p-5">
          <div class="flex items-center gap-2 text-label-md text-on-surface-variant"><span class="material-symbols-outlined text-amber-600">bolt</span>Charge</div>
          <p class="text-display-lg" id="fuel">0%</p>
          <div class="h-2 rounded-full bg-surface-container-high overflow-hidden"><div id="fuel-bar" class="h-full bg-amber-500" style="width:0%"></div></div>
        </div>
      </div>
    </div>

    <div class="lg:col-span-3 flex flex-col gap-md">
      <div class="h-[440px] rounded-2xl border border-outline-variant overflow-hidden relative">
        <div id="map"></div>
        <div class="absolute top-3 left-3 z-[400] bg-white/90 backdrop-blur px-3 py-2 rounded-lg border border-outline-variant text-label-sm font-bold flex items-center gap-2 pointer-events-none">
          <span class="material-symbols-outlined text-sm text-primary">my_location</span><span id="map-next">--</span></div>
      </div>
      <div class="bg-white rounded-2xl border border-outline-variant shadow-sm p-6">
        <h3 class="text-title-md flex items-center gap-2 mb-3"><span class="material-symbols-outlined text-secondary">smart_toy</span>Central AI instructions</h3>
        <div id="feed" class="font-mono text-sm space-y-1.5 max-h-40 overflow-y-auto"></div>
      </div>
    </div>
  </div>

  <div class="bg-white rounded-2xl border border-outline-variant shadow-sm p-4 flex flex-wrap items-center gap-3">
    <div class="flex items-center gap-2 text-label-md"><span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>Continuous shift</div>
    <div class="px-3 py-1 rounded-full bg-surface-container border border-outline-variant text-label-md">
      <span id="tick-label">Tick 01</span> &middot; <span id="time-label">T+5 min</span></div>
    <button id="play" class="px-4 py-2 bg-primary text-on-primary rounded-lg flex items-center gap-2 text-label-md"><span class="material-symbols-outlined" id="play-icon">pause</span><span id="play-text">Pause</span></button>
    <button id="prev" class="p-2 hover:bg-surface-container rounded-full text-on-surface-variant"><span class="material-symbols-outlined">skip_previous</span></button>
    <button id="next" class="p-2 hover:bg-surface-container rounded-full text-on-surface-variant"><span class="material-symbols-outlined">skip_next</span></button>
    <input id="scrub" type="range" min="0" value="0" class="flex-1 accent-primary min-w-[160px]"/>
    <select id="speed" class="rounded-lg border border-outline-variant bg-surface-container-lowest text-label-md py-1.5 px-2">
      <option value="1400">0.7x</option><option value="950" selected>1x</option><option value="500">2x</option><option value="250">4x</option></select>
  </div>
</div>

<div id="toast" class="fixed bottom-6 left-1/2 -translate-x-1/2 bg-inverse-surface text-inverse-on-surface px-5 py-3 rounded-xl shadow-lg opacity-0 pointer-events-none flex items-center gap-2 z-[600]">
  <span class="material-symbols-outlined text-sm">lock</span><span>Access restricted to Fleet Commander. Drivers cannot open admin modules.</span></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
const SIM = __DATA__;
const meta = SIM.meta, NAME = SIM.names, FALLBACK = SIM.latlng;
const _p = new URLSearchParams(location.search).get("truck");
const DRIVER = (_p && SIM.trucks[_p]) ? _p : SIM.default;
const frames = SIM.trucks[DRIVER];
const LL = {};
meta.nodes.forEach(n => { LL[n.id] = (n.lat!=null&&n.lng!=null)?[n.lat,n.lng]:FALLBACK[n.id]; });
const round = Math.round;
const STATUS = { IDLE:["Resting","#6d7a72"], EN_ROUTE:["En-route","#4b41e1"], SPRAYING:["Cleaning","#006948"],
                 STUCK:["Stuck","#ba1a1a"], REPLENISHING:["Replenishing","#b45309"] };

document.getElementById("truck-id").textContent = DRIVER;
document.getElementById("drv-initials").textContent = DRIVER.replace(/[^0-9]/g,"");

// locked-nav toast
const toast = document.getElementById("toast"); let toastT=null;
document.querySelectorAll(".nav-lock").forEach(b => b.onclick = () => {
  toast.style.opacity="1"; clearTimeout(toastT); toastT=setTimeout(()=>toast.style.opacity="0",2200); });

// map
const map = L.map('map',{ scrollWheelZoom:false, zoomControl:true });
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
  { attribution:'&copy; OpenStreetMap &copy; CARTO', subdomains:'abcd', maxZoom:19 }).addTo(map);
const pts = Object.values(LL).filter(Boolean); map.fitBounds(L.latLngBounds(pts).pad(0.06));
meta.links.forEach(l => { if(LL[l.s]&&LL[l.t]) L.polyline([LL[l.s],LL[l.t]],
  {color:l.color||"#9aa0a6",weight:l.line==="Service"?1.5:2.5,opacity:.35}).addTo(map); });
const routeLayer = L.layerGroup().addTo(map);
const truck = L.marker([28.62,77.2],{zIndexOffset:1000,icon:L.divIcon({className:"tk",iconSize:[30,30],iconAnchor:[15,15],
  html:`<div class="tkdot">${DRIVER.replace(/[^0-9]/g,"")}</div>`})}).addTo(map);
let targetMarker=null;

function llOf(t){ const a=LL[t.from]||LL[t.node]; if(!t.to||!LL[t.to]) return LL[t.node]||a;
  const b=LL[t.to]; return [a[0]+(b[0]-a[0])*t.frac,a[1]+(b[1]-a[1])*t.frac]; }
function haversine(a,b){ const R=6371,r=Math.PI/180;
  const dLa=(b[0]-a[0])*r,dLo=(b[1]-a[1])*r,la1=a[0]*r,la2=b[0]*r;
  const h=Math.sin(dLa/2)**2+Math.cos(la1)*Math.cos(la2)*Math.sin(dLo/2)**2; return 2*R*Math.asin(Math.sqrt(h)); }
function tagClass(l){ if(l.includes("EXCEPTION")||l.includes("STUCK"))return"text-error";
  if(l.includes("MISSION CLR")||l.includes("ON-SITE")||l.includes("RECOVERED"))return"text-primary";
  if(l.includes("SUPPLY")||l.includes("FASTPASS")||l.includes("REPLENISH"))return"text-amber-700";
  if(l.includes("DISPATCH")||l.includes("TOP-UP"))return"text-secondary"; return"text-on-surface-variant"; }

function render(i){
  const f=frames[i], t=f.t;
  document.getElementById("truck-class").textContent = t.class.charAt(0)+t.class.slice(1).toLowerCase()+" tanker";
  const [label,color]=STATUS[t.status]||["--","#6d7a72"];
  const pill=document.getElementById("status-pill");
  pill.textContent=label; pill.style.background=color; pill.style.color="#fff";
  document.getElementById("loc").textContent="at "+(NAME[t.node]||t.node);
  // lock banner
  const lb=document.getElementById("lock-banner"), lt=document.getElementById("lock-text");
  if(t.locked){ lb.classList.remove("hidden");
    lt.textContent = t.purpose.indexOf("REPLENISH")>=0 ? "Console locked: AI routing to depot to replenish." : "Console locked: AI-dictated route in progress."; }
  else if(t.status==="SPRAYING"){ lb.classList.remove("hidden"); lt.textContent="Cleaning in progress: cannons engaged by AI."; }
  else lb.classList.add("hidden");
  // mission
  const mission=document.getElementById("mission");
  if(t.status==="IDLE"){ mission.innerHTML='<span class="font-bold text-primary">Resting in reserve.</span> Awaiting dispatch at '+(NAME[t.node]||t.node)+'.'; }
  else if(t.purpose.indexOf("REPLENISH")>=0){ mission.innerHTML='<span class="font-bold text-amber-700">Replenishing.</span> Destination: '+(NAME[t.target]||t.target)+' depot.'; }
  else if(t.target){ mission.innerHTML='<span class="font-bold">Target hotspot:</span> '+(NAME[t.target]||t.target)+(f.taqi?(' &middot; <span class="text-error font-bold">AQI '+round(f.taqi)+'</span>'):''); }
  else mission.textContent="Standing by.";
  // route list (Dijkstra path from current index)
  const rl=document.getElementById("route-list"); rl.innerHTML="";
  const route=t.route||[]; const idx=t.route_idx||0;
  if(route.length<=1){ rl.innerHTML='<li class="text-label-md text-on-surface-variant p-2">No active route — unit stationary.</li>'; }
  let remKm=0;
  for(let k=0;k<route.length;k++){
    const done=k<idx, cur=k===idx, dest=k===route.length-1;
    if(k>idx && LL[route[k]] && LL[route[k-1]]) remKm+=haversine(LL[route[k-1]],LL[route[k]]);
    const dot=done?'<span class="material-symbols-outlined text-sm text-on-surface-variant">check_circle</span>'
      :cur?'<span class="material-symbols-outlined text-sm text-primary">my_location</span>'
      :dest?'<span class="material-symbols-outlined text-sm text-error">target</span>'
      :'<span class="material-symbols-outlined text-sm text-outline">radio_button_unchecked</span>';
    rl.insertAdjacentHTML("beforeend",
      `<li class="flex items-center gap-2 px-2 py-1 rounded ${cur?'bg-primary-container/20 font-bold':''} ${done?'opacity-50':''}">${dot}<span class="text-label-md">${NAME[route[k]]||route[k]}</span></li>`); }
  // next stop + map header
  const nextId = route[idx+1]||route[idx];
  document.getElementById("map-next").textContent = (t.status==="IDLE")?("Resting at "+(NAME[t.node]||t.node))
    :("Next: "+(NAME[nextId]||"--")+(remKm>0?(" · "+remKm.toFixed(1)+" km left"):""));
  // gauges
  document.getElementById("water").textContent=round(t.water)+"%";
  document.getElementById("fuel").textContent=round(t.fuel)+"%";
  document.getElementById("water-bar").style.width=round(t.water)+"%";
  document.getElementById("fuel-bar").style.width=round(t.fuel)+"%";
  // map: truck + route polyline + target
  const ll=llOf(t); if(ll) truck.setLatLng(ll);
  truck._icon && (truck._icon.firstChild.style.background=color,
                  truck._icon.firstChild.className="tkdot"+(t.stationary?" pulse":""));
  routeLayer.clearLayers();
  if(route.length>1){ const pts2=route.map(r=>LL[r]).filter(Boolean);
    routeLayer.addLayer(L.polyline(pts2,{color:color,weight:5,opacity:.85}));
    const remPts=route.slice(idx).map(r=>LL[r]).filter(Boolean);
    routeLayer.addLayer(L.polyline(remPts,{color:color,weight:5,opacity:1,dashArray:"1 8"})); }
  if(t.target&&LL[t.target]) routeLayer.addLayer(L.circleMarker(LL[t.target],{radius:9,color:"#ba1a1a",weight:3,fillColor:"#ffdad6",fillOpacity:.9}));
  // feed
  const feed=document.getElementById("feed"); feed.innerHTML="";
  const lines = f.ev.length ? f.ev : [synth(t)];
  lines.forEach(e=>feed.insertAdjacentHTML("beforeend",`<div class="ev ${tagClass(e)}">${e.replace(/</g,"&lt;")}</div>`));
  document.getElementById("tick-label").textContent="Tick "+String(f.tick).padStart(2,"0");
  document.getElementById("time-label").textContent="T+"+f.min+" min";
  document.getElementById("scrub").value=i;
}
function synth(t){ if(t.status==="IDLE")return"Resting in reserve. Standing by for AI dispatch.";
  if(t.purpose.indexOf("REPLENISH")>=0)return"Proceed to depot to replenish (console locked).";
  if(t.status==="SPRAYING")return"Hold position. Misting cannons engaged.";
  if(t.target)return"Proceed to "+(NAME[t.target]||t.target)+" via the Dijkstra-optimised route.";
  return"Awaiting instructions."; }

const scrub=document.getElementById("scrub"); scrub.max=frames.length-1;
let i=0,playing=false,timer=null;
function step(){ i=(i+1)%frames.length; render(i); }   // continuous loop
function play(){ playing=true; document.getElementById("play-icon").textContent="pause"; document.getElementById("play-text").textContent="Pause";
  timer=setInterval(step,+document.getElementById("speed").value); }
function stop(){ playing=false; document.getElementById("play-icon").textContent="play_arrow"; document.getElementById("play-text").textContent="Play"; clearInterval(timer); }
document.getElementById("play").onclick=()=>{ playing?stop():play(); };
document.getElementById("next").onclick=()=>{ stop(); i=Math.min(frames.length-1,i+1); render(i); };
document.getElementById("prev").onclick=()=>{ stop(); i=Math.max(0,i-1); render(i); };
document.getElementById("speed").onchange=()=>{ if(playing){ stop(); play(); } };
scrub.oninput=()=>{ stop(); i=+scrub.value; render(i); };
render(0); setTimeout(()=>{ map.invalidateSize(); play(); }, 350);
</script>
</body></html>
"""


def build_html(ticks: int, seed: int, truck: str | None) -> str:
    engine = SimulationEngine(seed=seed, verbose=False, topology="metro")
    engine.run_ticks(ticks)
    chosen = truck or pick_busiest_truck(engine.frames)
    payload = build_payload(engine, chosen)
    return _TEMPLATE.replace("__DATA__", json.dumps(payload))


def main() -> None:
    p = argparse.ArgumentParser(description="Generate the EcoShield driver console.")
    p.add_argument("--ticks", type=int, default=40)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--truck", default=None, help="truck id (default: busiest unit)")
    p.add_argument("--out", default="driver.html")
    p.add_argument("--open", action="store_true")
    args = p.parse_args()
    html = build_html(args.ticks, args.seed, args.truck)
    out = os.path.abspath(args.out)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Wrote {out}  ({len(html)//1024} KB, {args.ticks} ticks)")
    print(f"  open '{out}'")
    if args.open:
        webbrowser.open("file://" + out)


if __name__ == "__main__":
    main()
