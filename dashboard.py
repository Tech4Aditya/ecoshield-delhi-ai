#!/usr/bin/env python3
"""
Generate the EcoShield Delhi admin dashboard (dashboard.html).

Runs the simulation, then renders a polished, data-driven operations console
built on the "Ecologic Intelligence System" design language (Tailwind + Inter +
Material Symbols, emerald/indigo palette). The placeholder map from the Stitch
template is replaced with a real, interactive Leaflet map of Delhi.

    python3 dashboard.py --open                  # metro network (default)
    python3 dashboard.py --topology core --open  # original 6-junction map
    python3 dashboard.py --ticks 24 --seed 42

The metro build plots the real Delhi Metro lines and stations; water sprinkler
tankers either CLEAN hotspots (spraying / en-route) or REST in reserve at depots.
No emojis anywhere -- all iconography uses the Material Symbols outline font.
"""

from __future__ import annotations

import argparse
import json
import os
import webbrowser

from smog_control import SimulationEngine

# Fallback coordinates for the 6-junction "core" topology (metro nodes carry
# their own lat/lng inside viz_meta).
CORE_LATLNG = {
    "AV": [28.6469, 77.3152], "ITO": [28.6286, 77.2419], "CP": [28.6315, 77.2167],
    "DWK": [28.5921, 77.0460], "PRG": [28.6759, 77.0980], "AIIMS": [28.5672, 77.2100],
    "OKH": [28.5430, 77.2730], "NJF": [28.6090, 76.9790], "ROH": [28.7160, 77.1170],
    "DCG": [28.5800, 77.0590],
}

# Basemap provider. Paste a Mappls (MapmyIndia) Map/Raster API key here to switch
# every map to Mappls; left empty, the app uses a keyless, detailed street basemap.
MAPPLS_KEY = ""


def tile_config() -> tuple:
    """Return ``(url_json, opts_js)`` for the Leaflet basemap tile layer."""
    if MAPPLS_KEY:
        url = "https://apis.mappls.com/advancedmaps/v1/" + MAPPLS_KEY + "/tile/{z}/{x}/{y}.png"
        return json.dumps(url), '{attribution:"Mappls (MapmyIndia)", maxZoom:18}'
    # Keyless, detailed street map (CARTO Voyager — OSM data, roads + labels).
    url = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
    return json.dumps(url), '{attribution:"OpenStreetMap, CARTO", subdomains:"abcd", maxZoom:19}'

_TEMPLATE = r"""<!DOCTYPE html>
<html class="light" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>EcoShield Delhi | Metro Pollution-Control Command</title>
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
      "surface-container-high":"#e6e8ea","surface-container-highest":"#e0e3e5","outline":"#6d7a72","outline-variant":"#bccac0",
      "inverse-surface":"#2d3133","inverse-on-surface":"#eff1f3" },
    borderRadius:{ "DEFAULT":"0.25rem","lg":"0.5rem","xl":"0.75rem","2xl":"1rem","full":"9999px" },
    spacing:{ "xs":"0.5rem","sm":"1rem","md":"1.5rem","lg":"2rem","xl":"3rem","gutter":"1.5rem","margin-desktop":"2.5rem" },
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
  .glass-card{ background:rgba(255,255,255,0.85); backdrop-filter:blur(12px); border:1px solid rgba(255,255,255,0.4); }
  ::-webkit-scrollbar{ width:6px; height:6px; }
  ::-webkit-scrollbar-thumb{ background:#bccac0; border-radius:10px; }
  #map{ height:100%; width:100%; background:#e8edf0; z-index:0; }
  .leaflet-container{ font-family:Inter,sans-serif; }
  .leaflet-marker-icon.tanker-wrap{ transition:transform .6s linear; background:transparent; border:none; }
  .tanker{ width:24px; height:24px; border-radius:9999px; border:2px solid #fff; color:#fff; font-size:10px;
           font-weight:700; display:flex; align-items:center; justify-content:center; box-shadow:0 1px 4px rgba(0,0,0,.35); cursor:pointer; }
  .tanker.mist{ animation:pulse 1.1s ease-in-out infinite; }
  .node-label{ background:#fff; border:1px solid #bccac0; border-radius:6px; box-shadow:0 1px 3px rgba(0,0,0,.12);
               font-weight:600; font-size:11px; color:#191c1e; padding:1px 6px; }
  @keyframes pulse{ 0%,100%{ box-shadow:0 0 0 0 rgba(186,26,26,.55) } 50%{ box-shadow:0 0 0 9px rgba(186,26,26,0) } }
  .ev{ animation:fadein .4s ease; } @keyframes fadein{ from{opacity:0} to{opacity:1} }
  .nav-item{ margin:0 .5rem; padding:.75rem 1rem; display:flex; align-items:center; gap:.75rem;
             border-radius:9999px; color:#3d4a42; cursor:pointer; }
  .nav-item:hover{ background:#e6e8ea; }
  .nav-item.active{ background:#645efb; color:#fffbff; }
  .vtab th{ padding:.5rem .75rem; }
  .vtab tbody tr{ border-top:1px solid #e0e3e5; }
  .vtab tbody tr:hover{ background:#f2f4f6; }
</style>
</head>
<body class="bg-background text-on-surface">
<aside class="h-full w-72 left-0 top-0 fixed bg-surface-container-low border-r border-outline-variant z-40 hidden lg:flex flex-col py-md">
  <div class="px-6 py-4 flex items-center gap-3">
    <span class="material-symbols-outlined text-primary text-3xl">hub</span>
    <h1 class="text-headline-lg text-primary font-semibold">EcoShield</h1>
  </div>
  <nav class="flex flex-col mt-4 gap-1">
    <a class="nav-item" data-view="control" href="#"><span class="material-symbols-outlined">dashboard</span><span class="text-label-md">Admin Control</span></a>
    <a class="nav-item" data-view="fleet" href="#"><span class="material-symbols-outlined">local_shipping</span><span class="text-label-md">Fleet Operations</span></a>
    <a class="text-on-surface-variant mx-2 px-4 py-3 flex items-center gap-3 hover:bg-surface-container-high rounded-full" href="driver.html" target="_blank">
      <span class="material-symbols-outlined">badge</span><span class="text-label-md">Driver Portal</span><span class="material-symbols-outlined text-sm ml-auto">open_in_new</span></a>
    <a class="nav-item" data-view="metro" href="#"><span class="material-symbols-outlined">subway</span><span class="text-label-md">Metro Network</span></a>
    <a class="nav-item" data-view="routing" href="#"><span class="material-symbols-outlined">route</span><span class="text-label-md">Routing Engine</span></a>
    <a class="nav-item" data-view="health" href="#"><span class="material-symbols-outlined">settings_input_component</span><span class="text-label-md">System Health</span></a>
  </nav>
  <div class="mt-auto px-6 py-4 border-t border-outline-variant">
    <div class="flex items-center gap-3">
      <div class="w-10 h-10 rounded-full bg-primary-container flex items-center justify-center text-on-primary-container font-bold">CA</div>
      <div><p class="text-label-md font-semibold">Central AI Coordinator</p>
           <p class="text-label-sm text-on-surface-variant">Autonomous Dispatcher</p></div>
    </div>
  </div>
</aside>

<main class="lg:ml-72 min-h-screen flex flex-col pb-24 lg:pb-0">
  <header class="w-full top-0 sticky z-30 flex flex-wrap gap-3 justify-between items-center px-margin-desktop py-3 bg-surface/80 backdrop-blur-md border-b border-outline-variant">
    <div class="flex items-center gap-4">
      <h2 class="text-title-md text-primary">EcoShield Delhi</h2>
      <div class="h-6 w-px bg-outline-variant"></div>
      <div class="flex items-center gap-2 text-label-md text-on-surface-variant">
        <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>Live AI stream active</div>
    </div>
    <div class="flex items-center gap-3">
      <a href="driver.html" target="_blank" class="flex items-center gap-2 px-4 py-2 border border-outline-variant rounded-full text-label-md hover:bg-surface-container" title="Admin can open the restricted driver console">
        <span class="material-symbols-outlined text-sm">swap_horiz</span>Driver Portal</a>
      <div class="px-4 py-1.5 rounded-full bg-surface-container border border-outline-variant text-label-md">
        <span id="tick-label">Tick 01</span><span class="text-on-surface-variant"> &middot; </span><span id="time-label">T+5 min</span></div>
      <div class="flex items-center gap-1">
        <button id="prev" class="p-2 hover:bg-surface-container rounded-full text-on-surface-variant" aria-label="Previous tick"><span class="material-symbols-outlined">skip_previous</span></button>
        <button id="play" class="px-4 py-2 bg-primary text-on-primary rounded-lg flex items-center gap-2 text-label-md"><span class="material-symbols-outlined" id="play-icon">play_arrow</span><span id="play-text">Play</span></button>
        <button id="next" class="p-2 hover:bg-surface-container rounded-full text-on-surface-variant" aria-label="Next tick"><span class="material-symbols-outlined">skip_next</span></button>
      </div>
      <input id="scrub" type="range" min="0" value="0" class="w-32 accent-primary"/>
      <select id="speed" class="rounded-lg border border-outline-variant bg-surface-container-lowest text-label-md py-1.5 px-2">
        <option value="1400">0.7x</option><option value="950" selected>1x</option><option value="500">2x</option><option value="250">4x</option></select>
    </div>
  </header>

  <div class="p-margin-desktop flex flex-col gap-lg" data-view-panel="control">
    <section class="grid grid-cols-2 xl:grid-cols-4 gap-md">
      <div class="bg-white p-6 rounded-2xl border border-outline-variant shadow-sm relative overflow-hidden">
        <div class="flex justify-between items-start"><span class="text-label-md text-on-surface-variant">Network mean PM2.5</span>
          <span class="material-symbols-outlined" id="aqi-trend">trending_flat</span></div>
        <div class="mt-4"><h3 class="text-display-lg" id="s-aqi">0</h3><p class="text-label-sm font-bold" id="s-aqi-d">ug/m3</p></div>
        <span class="material-symbols-outlined text-8xl absolute -bottom-4 -right-3 opacity-10">cloud</span>
      </div>
      <div class="bg-white p-6 rounded-2xl border border-outline-variant shadow-sm relative overflow-hidden">
        <div class="flex justify-between items-start"><span class="text-label-md text-on-surface-variant">Active hotspots</span>
          <span class="material-symbols-outlined text-error">warning</span></div>
        <div class="mt-4"><h3 class="text-display-lg" id="s-hot">0</h3><p class="text-label-sm text-on-surface-variant font-bold" id="s-hot-d">0 predictive</p></div>
        <span class="material-symbols-outlined text-8xl absolute -bottom-4 -right-3 opacity-10">e911_emergency</span>
      </div>
      <div class="bg-white p-6 rounded-2xl border border-outline-variant shadow-sm relative overflow-hidden">
        <div class="flex justify-between items-start"><span class="text-label-md text-on-surface-variant">Tankers cleaning</span>
          <span class="material-symbols-outlined text-primary">cleaning_services</span></div>
        <div class="mt-4"><h3 class="text-display-lg" id="s-clean">0</h3><p class="text-label-sm text-primary font-bold" id="s-clean-d">0 resting in reserve</p></div>
        <span class="material-symbols-outlined text-8xl absolute -bottom-4 -right-3 opacity-10">water_drop</span>
      </div>
      <div class="bg-white p-6 rounded-2xl border border-outline-variant shadow-sm relative overflow-hidden">
        <div class="flex justify-between items-start"><span class="text-label-md text-on-surface-variant">Missions resolved</span>
          <span class="material-symbols-outlined text-secondary">task_alt</span></div>
        <div class="mt-4"><h3 class="text-display-lg" id="s-res">0</h3><p class="text-label-sm text-secondary font-bold" id="s-res-d">mitigated</p></div>
        <span class="material-symbols-outlined text-8xl absolute -bottom-4 -right-3 opacity-10">verified</span>
      </div>
    </section>

    <section class="grid grid-cols-1 lg:grid-cols-4 gap-md">
      <div class="lg:col-span-3 h-[620px] rounded-2xl border border-outline-variant overflow-hidden relative">
        <div id="map"></div>
        <div class="absolute top-4 left-4 z-[400] flex flex-col gap-2 pointer-events-none">
          <div class="glass-card px-4 py-2 rounded-full flex items-center gap-2 shadow-sm"><span class="w-3 h-3 rounded-full bg-emerald-500"></span><span class="text-label-sm">Healthy &lt;120</span></div>
          <div class="glass-card px-4 py-2 rounded-full flex items-center gap-2 shadow-sm"><span class="w-3 h-3 rounded-full bg-amber-500"></span><span class="text-label-sm">Poor 120-250</span></div>
          <div class="glass-card px-4 py-2 rounded-full flex items-center gap-2 shadow-sm"><span class="w-3 h-3 rounded-full bg-red-500"></span><span class="text-label-sm">Severe &gt;250</span></div>
          <div class="glass-card px-4 py-2 rounded-full flex items-center gap-3 shadow-sm">
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-primary border-2 border-white"></span><span class="text-label-sm">Cleaning</span></span>
            <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-white border-2 border-outline"></span><span class="text-label-sm">Resting</span></span>
          </div>
        </div>
        <div class="absolute bottom-5 left-5 right-5 z-[400]">
          <div class="glass-card p-4 rounded-xl flex flex-wrap gap-3 justify-between items-center">
            <div class="flex items-center gap-4">
              <div class="p-2 bg-primary-container rounded-lg text-on-primary-container"><span class="material-symbols-outlined">subway</span></div>
              <div><h4 class="text-label-md font-bold">Delhi Metro network &middot; live fleet</h4><p class="text-xs text-on-surface-variant" id="map-fleet">tracking tankers</p>
                <p class="text-xs text-secondary font-bold mt-0.5">Tip: click any tanker to open its driver console</p></div>
            </div>
            <div class="flex gap-2">
              <button id="toggle-roads" class="px-4 py-2 bg-primary text-white rounded-lg text-label-sm font-bold flex items-center gap-1"><span class="material-symbols-outlined text-sm">route</span>Lines</button>
              <button id="toggle-zones" class="px-4 py-2 bg-secondary text-white rounded-lg text-label-sm font-bold flex items-center gap-1"><span class="material-symbols-outlined text-sm">blur_on</span>Heat zones</button>
              <a href="driver.html" target="_blank" class="px-4 py-2 bg-surface-container-high text-on-surface rounded-lg text-label-sm font-bold flex items-center gap-1"><span class="material-symbols-outlined text-sm">badge</span>Driver Portal</a>
            </div>
          </div>
        </div>
      </div>
      <div class="lg:col-span-1">
        <div class="bg-white p-6 rounded-2xl border border-outline-variant shadow-sm h-[620px] flex flex-col">
          <h4 class="text-title-md flex items-center gap-2 mb-4"><span class="material-symbols-outlined text-error">warning</span>Critical hotspots</h4>
          <div id="hotspots" class="space-y-3 overflow-y-auto pr-1 flex-1"></div>
        </div>
      </div>
    </section>

    <section class="grid grid-cols-1 lg:grid-cols-2 gap-lg">
      <div class="bg-white p-8 rounded-2xl border border-outline-variant shadow-sm flex flex-col">
        <div class="flex justify-between items-center mb-6">
          <div><h3 class="text-headline-lg">Agentic fleet management</h3><p class="text-on-surface-variant">Cleaning duty vs resting reserve</p></div>
          <span class="material-symbols-outlined text-secondary text-4xl">automation</span></div>
        <div class="grid grid-cols-2 gap-4" id="fleet-grid"></div>
        <div class="mt-6 bg-indigo-50 border-l-4 border-secondary p-4 rounded-r-lg">
          <div class="flex items-start gap-3"><span class="material-symbols-outlined text-secondary">psychology</span>
            <div><p class="text-label-md font-bold text-indigo-900">AI logic note</p><p class="text-sm text-indigo-800" id="ai-note">Initialising coordinator...</p></div></div>
        </div>
      </div>
      <div class="bg-white p-8 rounded-2xl border border-outline-variant shadow-sm flex flex-col">
        <div class="flex justify-between items-center mb-6">
          <div><h3 class="text-headline-lg">Mitigation impact</h3><p class="text-on-surface-variant">Network PM2.5 trajectory</p></div>
          <span class="material-symbols-outlined text-primary text-4xl">eco</span></div>
        <div class="text-center mb-4"><div class="inline-flex items-end gap-2">
          <h4 class="text-6xl font-extrabold text-primary" id="imp-aqi">0</h4><span class="text-title-md font-bold text-on-surface-variant pb-2">ug/m3</span></div>
          <p class="font-bold text-on-surface-variant tracking-widest uppercase text-xs mt-1">current network mean</p></div>
        <div class="flex-1 flex items-end justify-center gap-2 h-40" id="trend"></div>
        <div class="grid grid-cols-2 gap-3 mt-6">
          <div class="p-4 rounded-xl bg-surface-container-low text-center"><p class="text-2xl font-bold text-primary" id="imp-bill">0</p><p class="text-xs text-on-surface-variant font-bold uppercase tracking-wider">Fast-pass INR</p></div>
          <div class="p-4 rounded-xl bg-surface-container-low text-center"><p class="text-2xl font-bold text-secondary" id="imp-act">0</p><p class="text-xs text-on-surface-variant font-bold uppercase tracking-wider">Active missions</p></div>
        </div>
      </div>
    </section>

    <section class="bg-white p-8 rounded-2xl border border-outline-variant shadow-sm">
      <div class="flex justify-between items-center mb-4">
        <div><h3 class="text-headline-lg">AI coordinator stream</h3><p class="text-on-surface-variant">Decisions taken this tick</p></div>
        <span class="material-symbols-outlined text-tertiary text-4xl">terminal</span></div>
      <div id="log" class="font-mono text-sm space-y-1.5 max-h-72 overflow-y-auto"></div>
    </section>
  </div>

  <div class="p-margin-desktop hidden" data-view-panel="fleet">
    <div class="flex items-center gap-3 mb-6"><span class="material-symbols-outlined text-primary text-3xl">local_shipping</span>
      <div><h2 class="text-headline-lg">Fleet Operations</h2><p class="text-on-surface-variant">All tankers, live &middot; click a row to open that driver's console</p></div></div>
    <div class="bg-white rounded-2xl border border-outline-variant shadow-sm overflow-hidden">
      <table class="w-full text-label-md vtab"><thead class="bg-surface-container-low text-on-surface-variant text-label-sm uppercase text-left">
        <tr><th>Unit</th><th>Class</th><th>Status</th><th>Location</th><th>Target</th><th>Water</th><th>Charge</th><th></th></tr></thead>
        <tbody id="fleet-table"></tbody></table></div>
  </div>

  <div class="p-margin-desktop hidden" data-view-panel="metro">
    <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
      <div class="flex items-center gap-3"><span class="material-symbols-outlined text-primary text-3xl">subway</span>
        <div><h2 class="text-headline-lg">Metro Network</h2><p class="text-on-surface-variant">Live station air quality across all lines</p></div></div>
      <div id="metro-counts" class="flex gap-2 flex-wrap"></div></div>
    <div class="bg-white rounded-2xl border border-outline-variant shadow-sm overflow-hidden">
      <table class="w-full text-label-md vtab"><thead class="bg-surface-container-low text-on-surface-variant text-label-sm uppercase text-left">
        <tr><th>Station</th><th>Lines</th><th>PM2.5</th><th>Band</th><th>Status</th></tr></thead>
        <tbody id="metro-table"></tbody></table></div>
  </div>

  <div class="p-margin-desktop hidden" data-view-panel="routing">
    <div class="flex items-center gap-3 mb-6"><span class="material-symbols-outlined text-primary text-3xl">route</span>
      <div><h2 class="text-headline-lg">Routing Engine</h2><p class="text-on-surface-variant">Modified multi-objective Dijkstra &middot; shortest-time path between stations</p></div></div>
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-md">
      <div class="bg-white rounded-2xl border border-outline-variant shadow-sm p-6 flex flex-col gap-3">
        <span class="px-2 py-1 self-start rounded-full bg-secondary-container text-on-secondary-container text-label-sm font-bold">Algorithm: Dijkstra</span>
        <label class="text-label-sm text-on-surface-variant">Origin</label><select id="r-from" class="rounded-lg border border-outline-variant p-2 bg-surface-container-lowest"></select>
        <label class="text-label-sm text-on-surface-variant">Destination</label><select id="r-to" class="rounded-lg border border-outline-variant p-2 bg-surface-container-lowest"></select>
        <button id="r-go" class="px-4 py-2 bg-primary text-white rounded-lg font-bold flex items-center justify-center gap-2"><span class="material-symbols-outlined text-sm">bolt</span>Compute shortest path</button>
        <div id="r-out" class="text-label-md"></div>
        <ol id="r-path" class="space-y-1 max-h-72 overflow-y-auto"></ol>
      </div>
      <div class="lg:col-span-2 h-[540px] rounded-2xl border border-outline-variant overflow-hidden"><div id="rmap" style="height:100%;width:100%"></div></div>
    </div>
  </div>

  <div class="p-margin-desktop hidden" data-view-panel="health">
    <div class="flex items-center gap-3 mb-6"><span class="material-symbols-outlined text-primary text-3xl">settings_input_component</span>
      <div><h2 class="text-headline-lg">System Health</h2><p class="text-on-surface-variant">Live platform &amp; coordinator telemetry</p></div></div>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-md" id="health-cards"></div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-md mt-6">
      <div class="bg-white rounded-2xl border border-outline-variant shadow-sm p-6"><h3 class="text-title-md mb-3">Fleet status</h3><div id="health-fleet" class="space-y-2"></div></div>
      <div class="bg-white rounded-2xl border border-outline-variant shadow-sm p-6"><h3 class="text-title-md mb-3">Subsystems</h3><div id="health-sub" class="space-y-2"></div></div>
    </div>
  </div>

  <footer class="w-full py-lg mt-auto bg-surface-container-highest flex flex-col md:flex-row justify-between items-center px-margin-desktop gap-md border-t border-outline-variant">
    <div class="flex items-center gap-4"><span class="text-title-md">EcoShield Delhi</span>
      <span class="text-label-sm text-on-surface-variant">Agentic AI Pollution-Control System</span></div>
    <div class="flex gap-lg text-label-sm text-on-surface-variant">
      <span id="foot-net">Delhi Metro network</span><span>Modified multi-objective Dijkstra</span></div>
  </footer>
</main>

<nav class="lg:hidden fixed bottom-0 left-0 w-full flex justify-around items-center h-20 bg-surface border-t border-outline-variant z-50">
  <a class="flex flex-col items-center text-on-surface-variant" data-view="control" href="#"><span class="material-symbols-outlined">dashboard</span><span class="text-label-sm">Control</span></a>
  <a class="flex flex-col items-center text-on-surface-variant" data-view="metro" href="#"><span class="material-symbols-outlined">subway</span><span class="text-label-sm">Network</span></a>
  <a class="flex flex-col items-center text-on-surface-variant" data-view="fleet" href="#"><span class="material-symbols-outlined">local_shipping</span><span class="text-label-sm">Fleet</span></a>
  <a class="flex flex-col items-center text-on-surface-variant" data-view="health" href="#"><span class="material-symbols-outlined">monitor_heart</span><span class="text-label-sm">Health</span></a>
</nav>

<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
const SIM = __DATA__;
const meta = SIM.meta, frames = SIM.frames, FALLBACK = SIM.latlng;
const NAME = {}, TYPE = {}, LL = {};
meta.nodes.forEach(n => { NAME[n.id]=n.name; TYPE[n.id]=n.type;
  LL[n.id] = (n.lat!=null && n.lng!=null) ? [n.lat,n.lng] : FALLBACK[n.id]; });
const JUNCTIONS = meta.nodes.filter(n => n.type==="JUNCTION").map(n=>n.id);
document.getElementById("foot-net").textContent = JUNCTIONS.length+" stations · "+meta.fleet.length+" tankers";

// Road-following geometry per edge (both directions) so paths follow real streets.
const GEOM={};
meta.links.forEach(l=>{ if(l.geom&&l.geom.length>1){ GEOM[l.s+'|'+l.t]=l.geom; GEOM[l.t+'|'+l.s]=l.geom.slice().reverse(); } });
function segGeom(a,b){ return GEOM[a+'|'+b] || ((LL[a]&&LL[b])?[LL[a],LL[b]]:null); }
function hav(a,b){ const R=6371,r=Math.PI/180,dla=(b[0]-a[0])*r,dlo=(b[1]-a[1])*r,la1=a[0]*r,la2=b[0]*r;
  const h=Math.sin(dla/2)**2+Math.cos(la1)*Math.cos(la2)*Math.sin(dlo/2)**2; return 2*R*Math.asin(Math.sqrt(h)); }
function pointAlong(pts,frac){ if(!pts||pts.length<2) return pts?pts[0]:null;
  if(frac<=0)return pts[0]; if(frac>=1)return pts[pts.length-1];
  let tot=0,seg=[]; for(let k=1;k<pts.length;k++){const d=hav(pts[k-1],pts[k]);seg.push(d);tot+=d;}
  let tgt=frac*tot,acc=0; for(let k=1;k<pts.length;k++){const d=seg[k-1]; if(acc+d>=tgt){const r=(tgt-acc)/(d||1);
    return [pts[k-1][0]+(pts[k][0]-pts[k-1][0])*r, pts[k-1][1]+(pts[k][1]-pts[k-1][1])*r];} acc+=d;} return pts[pts.length-1]; }
function routeGeom(path){ let out=[]; for(let k=1;k<path.length;k++){ const g=segGeom(path[k-1],path[k]); if(g&&g.length){ out=out.length?out.concat(g.slice(1)):g.slice(); } } return out; }

function aqiColor(a){ if(a<120) return "#10b981"; if(a<250) return "#f59e0b"; return "#ef4444"; }
const STATUS = { IDLE:"#6d7a72", EN_ROUTE:"#4b41e1", SPRAYING:"#006948", STUCK:"#ba1a1a", REPLENISHING:"#b45309" };
const round = Math.round;

function baseLayer(){ return L.tileLayer(__TILE_URL__, __TILE_OPTS__); }
const map = L.map('map',{ scrollWheelZoom:false, zoomControl:true });
baseLayer().addTo(map);
const pts = Object.values(LL).filter(Boolean);
map.fitBounds(L.latLngBounds(pts).pad(0.06));

const roadLayer = L.layerGroup().addTo(map);
const zoneLayer = L.layerGroup().addTo(map);
const congLayer = L.layerGroup().addTo(map);
meta.links.forEach(l => { const g=segGeom(l.s,l.t); if(g){ const svc = l.line==="Service";
  roadLayer.addLayer(L.polyline(g,
    {color:l.color||"#9aa0a6", weight:svc?2:4, opacity:svc?.45:.7, dashArray:svc?"3 6":null})); } });

const zoneEls = {}, dotEls = {}, truckEls = {};
meta.nodes.forEach(n => {
  if(!LL[n.id]) return;
  if(n.type==="JUNCTION"){
    zoneEls[n.id] = L.circle(LL[n.id],{radius:500,color:"#10b981",weight:1,fillColor:"#10b981",fillOpacity:.14}).addTo(zoneLayer);
    dotEls[n.id] = L.circleMarker(LL[n.id],{radius:5,color:"#fff",weight:1.5,fillColor:"#10b981",fillOpacity:1}).addTo(map);
    dotEls[n.id].bindTooltip(n.name,{direction:"top",className:"node-label"});
  } else {
    const icon = n.type==="STP" ? "water_drop" : "ev_station";
    dotEls[n.id] = L.marker(LL[n.id],{icon:L.divIcon({className:"",iconSize:[24,24],iconAnchor:[12,12],
      html:`<div style="width:24px;height:24px;border-radius:6px;background:#1f6feb;border:2px solid #fff;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(0,0,0,.3)"><span class="material-symbols-outlined" style="font-size:14px;color:#fff">${icon}</span></div>`})}).addTo(map);
    dotEls[n.id].bindTooltip(n.name+" (depot)",{direction:"top",className:"node-label"});
  }
});
meta.fleet.forEach(t => {
  const mk = L.marker([28.62,77.2],{ zIndexOffset:1000, icon:L.divIcon({className:"tanker-wrap",
    iconSize:[24,24], iconAnchor:[12,12], html:`<div class="tanker" style="background:#6d7a72">${t.id.replace(/[^0-9]/g,"")}</div>`}) }).addTo(map);
  mk.bindTooltip(t.id+" — open driver console",{direction:"top",className:"node-label"});
  mk.on("click", ()=>window.open("driver.html?truck="+encodeURIComponent(t.id),"_blank"));
  truckEls[t.id] = mk;
});

function truckLatLng(t){ if(!t.to||!LL[t.to]) return LL[t.node]||LL[t.from];
  const g=segGeom(t.from,t.to); if(g) return pointAlong(g,t.frac);
  const a=LL[t.from],b=LL[t.to]; return [a[0]+(b[0]-a[0])*t.frac,a[1]+(b[1]-a[1])*t.frac]; }
function isCleaning(s){ return s==="EN_ROUTE"||s==="SPRAYING"; }

function tagClass(l){
  if(l.includes("EXCEPTION")||l.includes("STUCK")) return "text-error";
  if(l.includes("PREDICT")) return "text-amber-600";
  if(l.includes("DISPATCH")||l.includes("TOP-UP")) return "text-secondary";
  if(l.includes("MISSION CLR")||l.includes("ON-SITE")||l.includes("RECOVERED")) return "text-primary";
  if(l.includes("SUPPLY")||l.includes("FASTPASS")||l.includes("REPLENISH")) return "text-amber-700";
  return "text-on-surface-variant"; }

let prevMean = null;
let activeView = "control";
function meanAqi(f){ const v=f.nodes.filter(n=>JUNCTIONS.includes(n.id)); return round(v.reduce((a,n)=>a+n.aqi,0)/v.length); }
const TREND = frames.map(meanAqi); const TMAX = Math.max(...TREND);

function render(i){
  const f = frames[i];
  if(activeView==="control"){
    f.nodes.forEach(n => {
      const z = zoneEls[n.id], d = dotEls[n.id]; const col = aqiColor(n.aqi);
      if(z){ z.setStyle({color:col,fillColor:col,fillOpacity:n.hotspot?.30:.13,weight:n.hotspot?3:1});
             z.setRadius(420 + Math.max(0,n.aqi-80)*4); }
      if(d && d.setStyle){ d.setStyle({fillColor:col, radius:n.hotspot?7:5});
        d.setTooltipContent(`${NAME[n.id]} · PM2.5 ${round(n.aqi)}`); }
    });
    congLayer.clearLayers();
    f.congested.forEach(c => { const g=segGeom(c.s,c.t); if(g){ const grid=c.factor>=6;
      congLayer.addLayer(L.polyline(g,{color:grid?"#ba1a1a":"#f59e0b",weight:grid?6:4,opacity:.9,dashArray:grid?"3 8":"8 6"})); } });
    f.trucks.forEach(t => { const m = truckEls[t.id]; if(!m) return;
      const ll = truckLatLng(t); if(ll) m.setLatLng(ll);
      if(m._icon){ const dot=m._icon.firstChild; const col=STATUS[t.status]||"#6d7a72"; const resting=(t.status==="IDLE");
        dot.style.background = resting ? "#ffffff" : col;
        dot.style.color = resting ? "#3d4a42" : "#ffffff";
        dot.style.borderColor = resting ? col : "#ffffff";
        dot.className = "tanker"+(t.stationary?" mist":"");
        m._icon.title = `${t.id} ${t.class} · ${t.status} · water ${round(t.water)}% · fuel ${round(t.fuel)}%`; } });
  } else {
    if(activeView==="fleet" && window.buildFleet) buildFleet(f);
    else if(activeView==="metro" && window.buildMetro) buildMetro(f);
    else if(activeView==="health" && window.buildHealth) buildHealth(f);
  }

  const mean = meanAqi(f);
  document.getElementById("s-aqi").textContent = mean;
  const dEl = document.getElementById("s-aqi-d"), tr = document.getElementById("aqi-trend");
  if(prevMean===null){ dEl.textContent="ug/m3 baseline"; dEl.className="text-label-sm font-bold text-on-surface-variant"; tr.textContent="trending_flat"; tr.className="material-symbols-outlined text-on-surface-variant"; }
  else { const dv=mean-prevMean; const up=dv>0;
    dEl.textContent=(up?"+":"")+dv+" vs last tick"; dEl.className="text-label-sm font-bold "+(up?"text-error":"text-primary");
    tr.textContent=up?"trending_up":(dv<0?"trending_down":"trending_flat"); tr.className="material-symbols-outlined "+(up?"text-error":"text-primary"); }
  prevMean = mean;
  const hot=f.nodes.filter(n=>n.hotspot).length, pred=f.nodes.filter(n=>n.predictive).length;
  document.getElementById("s-hot").textContent=hot;
  document.getElementById("s-hot-d").textContent=pred+" predictive";
  const cleaning=f.trucks.filter(t=>isCleaning(t.status)).length;
  const resting=f.trucks.filter(t=>t.status==="IDLE").length;
  document.getElementById("s-clean").textContent=cleaning;
  document.getElementById("s-clean-d").textContent=resting+" resting in reserve";
  document.getElementById("s-res").textContent=f.missions_resolved;
  document.getElementById("tick-label").textContent="Tick "+String(f.tick).padStart(2,"0");
  document.getElementById("time-label").textContent="T+"+f.minute+" min";
  const repl=f.trucks.filter(t=>t.status==="REPLENISHING").length;
  document.getElementById("map-fleet").textContent=cleaning+" cleaning · "+resting+" resting · "+repl+" replenishing";

  const hs=document.getElementById("hotspots"); hs.innerHTML="";
  const crit=f.nodes.filter(n=>n.hotspot||n.predictive).sort((a,b)=>b.aqi-a.aqi);
  if(crit.length===0) hs.innerHTML='<div class="text-sm text-on-surface-variant p-4 text-center bg-surface-container-low rounded-xl">No active hotspots. Network nominal; fleet resting.</div>';
  crit.forEach(n => { const sev=n.aqi>=250; const note=(f.events.find(e=>e.includes(NAME[n.id]))||"").replace(/^\s*\[[^\]]*\]\s*/,"");
    const badge=sev?"bg-error-container text-on-error-container":"bg-amber-100 text-amber-800";
    const bar=n.predictive?"border-secondary":(sev?"border-error":"border-amber-500");
    const tag=n.predictive?"Predicted":(sev?"Severe":"Poor");
    hs.insertAdjacentHTML("beforeend",
      `<div class="p-4 bg-surface-container-low rounded-xl border-l-4 ${bar}">
        <div class="flex justify-between items-start mb-1"><span class="text-label-md font-bold">${NAME[n.id]}</span>
          <span class="text-xs px-2 py-0.5 ${badge} rounded-full font-bold">AQI ${round(n.aqi)}</span></div>
        <p class="text-xs text-on-surface-variant mb-2 italic">${note?('"'+note+'"'):(tag+" zone under AI watch.")}</p>
        <div class="flex justify-between items-center"><span class="text-label-sm font-medium">${n.predictive?"Pre-emptive curtain":"Mitigation active"}</span>
          <span class="material-symbols-outlined text-primary text-sm">${n.predictive?"schedule":"water_drop"}</span></div></div>`); });

  const c={SPRAYING:0,EN_ROUTE:0,REPLENISHING:0,IDLE:0,STUCK:0};
  f.trucks.forEach(t=>c[t.status]=(c[t.status]||0)+1);
  const cells=[
    ["Cleaning on-site",c.SPRAYING,"cleaning_services","bg-primary-container text-on-primary-container"],
    ["En-route to clean",c.EN_ROUTE,"navigation","bg-secondary-container text-on-secondary-container"],
    ["Resting (reserve)",c.IDLE,"local_parking","bg-surface-container-high text-on-surface-variant"],
    ["Replenishing",c.REPLENISHING+c.STUCK,"ev_station","bg-amber-100 text-amber-700"] ];
  document.getElementById("fleet-grid").innerHTML=cells.map(x=>
    `<div class="p-5 border border-outline-variant rounded-xl flex items-center gap-4">
      <div class="p-3 ${x[3]} rounded-lg"><span class="material-symbols-outlined" style="font-variation-settings:'FILL' 1">${x[2]}</span></div>
      <div><h5 class="font-bold text-label-md">${x[0]}</h5><p class="text-2xl font-bold">${x[1]} <span class="text-label-sm font-normal text-on-surface-variant">units</span></p></div></div>`).join("");
  const salient=f.events.find(e=>e.includes("EXCEPTION"))||f.events.find(e=>e.includes("MISSION CLR"))
    ||f.events.find(e=>e.includes("PREDICT"))||f.events.find(e=>e.includes("DISPATCH"))||f.events[0]
    ||"Holding pattern: monitoring station AQI sensors; reserve tankers resting.";
  document.getElementById("ai-note").textContent=salient.replace(/^\s*\[[^\]]*\]\s*/,"");

  document.getElementById("imp-aqi").textContent=mean;
  document.getElementById("imp-bill").textContent=f.billed;
  document.getElementById("imp-act").textContent=f.missions_active;
  const td=document.getElementById("trend"); td.innerHTML="";
  TREND.forEach((v,k)=>{ const h=Math.max(6,round(v/TMAX*150)); const cur=k===i;
    td.insertAdjacentHTML("beforeend",`<div title="Tick ${frames[k].tick}: ${v}" style="height:${h}px" class="w-full max-w-[22px] rounded-t-lg ${cur?'bg-primary':'bg-emerald-200'}"></div>`); });

  const log=document.getElementById("log"); log.innerHTML="";
  if(f.events.length===0) log.innerHTML='<div class="text-on-surface-variant">No coordinator actions this tick.</div>';
  f.events.forEach(e=>log.insertAdjacentHTML("beforeend",`<div class="ev ${tagClass(e)}">${e.replace(/</g,"&lt;")}</div>`));
  document.getElementById("scrub").value=i;
}

const scrub=document.getElementById("scrub"); scrub.max=frames.length-1;
let i=0, playing=false, timer=null;
function step(){ i=(i+1)%frames.length; render(i); }   // continuous loop, never stops
function play(){ playing=true; document.getElementById("play-icon").textContent="pause"; document.getElementById("play-text").textContent="Pause";
  timer=setInterval(step,+document.getElementById("speed").value); }
function stop(){ playing=false; document.getElementById("play-icon").textContent="play_arrow"; document.getElementById("play-text").textContent="Play"; clearInterval(timer); }
document.getElementById("play").onclick=()=>{ if(playing) stop(); else { if(i>=frames.length-1) i=0; play(); } };
document.getElementById("next").onclick=()=>{ stop(); i=Math.min(frames.length-1,i+1); render(i); };
document.getElementById("prev").onclick=()=>{ stop(); i=Math.max(0,i-1); render(i); };
document.getElementById("speed").onchange=()=>{ if(playing){ stop(); play(); } };
scrub.oninput=()=>{ stop(); i=+scrub.value; render(i); };
document.getElementById("toggle-roads").onclick=()=>{ map.hasLayer(roadLayer)?map.removeLayer(roadLayer):map.addLayer(roadLayer); };
document.getElementById("toggle-zones").onclick=()=>{ map.hasLayer(zoneLayer)?map.removeLayer(zoneLayer):map.addLayer(zoneLayer); };
render(0);
setTimeout(()=>{ map.invalidateSize(); play(); }, 350);   // continuous auto-play
</script>
<script>
// ---- Multi-view router: every sidebar item opens a real, data-driven page ----
const LINE={}; meta.nodes.forEach(n=>LINE[n.id]=n.line);

function showView(v){
  activeView=v;
  document.querySelectorAll('[data-view-panel]').forEach(p=>p.classList.toggle('hidden', p.getAttribute('data-view-panel')!==v));
  document.querySelectorAll('.nav-item').forEach(a=>a.classList.toggle('active', a.getAttribute('data-view')===v));
  if(v==='control'){ setTimeout(()=>{ map.invalidateSize(); render(i); },60); }
  else if(v==='routing'){ if(!window.rmap) initRouting(); else setTimeout(()=>rmap.invalidateSize(),60); }
  else { render(i); }
}

function badge(s){ const c=STATUS[s]||'#6d7a72'; return `<span class="px-2 py-0.5 rounded-full text-xs font-bold" style="background:${c};color:#fff">${s}</span>`; }
function buildFleet(f){
  document.getElementById('fleet-table').innerHTML=f.trucks.map(t=>{
    const loc=NAME[t.node]||t.node, tgt=t.target?(NAME[t.target]||t.target):'—';
    return `<tr class="cursor-pointer" onclick="window.open('driver.html?truck=${t.id}','_blank')">
      <td class="px-3 py-2 font-bold">${t.id}</td><td>${t.class}</td><td class="py-2">${badge(t.status)}</td>
      <td>${loc}</td><td>${tgt}</td><td>${round(t.water)}%</td><td>${round(t.fuel)}%</td>
      <td class="text-secondary pr-3"><span class="material-symbols-outlined text-sm">open_in_new</span></td></tr>`;
  }).join('');
}
function buildMetro(f){
  const band=a=>a<120?['Healthy','#10b981']:a<250?['Poor','#f59e0b']:['Severe','#ef4444'];
  const js=f.nodes.filter(n=>JUNCTIONS.includes(n.id)).slice().sort((a,b)=>b.aqi-a.aqi);
  document.getElementById('metro-table').innerHTML=js.map(n=>{ const [bn,bc]=band(n.aqi);
    const st=n.hotspot?'<span class="text-error font-bold">Hotspot — cleaning</span>':(n.predictive?'<span class="text-amber-600 font-bold">Predicted</span>':'<span class="text-on-surface-variant">Nominal</span>');
    return `<tr><td class="px-3 py-2 font-bold">${NAME[n.id]}</td><td class="text-xs text-on-surface-variant">${LINE[n.id]||''}</td>
      <td>${round(n.aqi)}</td><td><span class="px-2 py-0.5 rounded-full text-xs font-bold" style="background:${bc}22;color:${bc}">${bn}</span></td><td>${st}</td></tr>`;
  }).join('');
  const h=js.filter(n=>n.aqi<120).length, p=js.filter(n=>n.aqi>=120&&n.aqi<250).length, s=js.filter(n=>n.aqi>=250).length;
  document.getElementById('metro-counts').innerHTML=
    `<span class="px-3 py-1 rounded-full text-xs font-bold" style="background:#10b98122;color:#0f6e56">${h} healthy</span>
     <span class="px-3 py-1 rounded-full text-xs font-bold" style="background:#f59e0b22;color:#b45309">${p} poor</span>
     <span class="px-3 py-1 rounded-full text-xs font-bold" style="background:#ef444422;color:#ba1a1a">${s} severe</span>`;
}
function buildHealth(f){
  const stations=JUNCTIONS.length, depots=meta.nodes.length-stations, edges=meta.edges.length, fleet=meta.fleet.length;
  const cards=[['Stations',stations,'subway'],['Depots',depots,'ev_station'],['Directed edges',edges,'route'],['Fleet size',fleet,'local_shipping'],
    ['Mean PM2.5',meanAqi(f),'cloud'],['Active missions',f.missions_active,'e911_emergency'],['Resolved',f.missions_resolved,'task_alt'],['Fast-pass INR',f.billed,'payments']];
  document.getElementById('health-cards').innerHTML=cards.map(c=>
    `<div class="bg-white rounded-2xl border border-outline-variant shadow-sm p-5"><div class="flex justify-between text-on-surface-variant text-label-sm">${c[0]}<span class="material-symbols-outlined text-sm">${c[2]}</span></div><p class="text-3xl font-bold mt-1">${c[1]}</p></div>`).join('');
  const cnt={}; f.trucks.forEach(t=>cnt[t.status]=(cnt[t.status]||0)+1);
  const order=[['SPRAYING','Cleaning on-site','#006948'],['EN_ROUTE','En-route','#4b41e1'],['IDLE','Resting reserve','#6d7a72'],['REPLENISHING','Replenishing','#b45309'],['STUCK','Stuck','#ba1a1a']];
  document.getElementById('health-fleet').innerHTML=order.map(o=>{ const v=cnt[o[0]]||0, pct=round(v/fleet*100);
    return `<div><div class="flex justify-between text-label-md"><span>${o[1]}</span><span class="font-bold">${v}</span></div>
      <div class="h-2 rounded-full bg-surface-container-high overflow-hidden"><div style="width:${pct}%;background:${o[2]}" class="h-full"></div></div></div>`;}).join('');
  const subs=[['AI coordinator stream','nominal'],['Dijkstra routing engine','nominal'],['Telemetry ingest','nominal'],['STP water depots','online'],['CNG / charging depots','online']];
  document.getElementById('health-sub').innerHTML=subs.map(s=>
    `<div class="flex justify-between items-center"><span class="text-label-md">${s[0]}</span>
     <span class="flex items-center gap-1 text-primary font-bold text-label-sm"><span class="w-2 h-2 rounded-full bg-emerald-500"></span>${s[1]}</span></div>`).join('');
}

// ---- Routing Engine: in-browser Dijkstra over the directed weighted graph ----
const ADJ={}; meta.nodes.forEach(n=>ADJ[n.id]=[]);
meta.edges.forEach(e=>{ if(ADJ[e.s]) ADJ[e.s].push([e.t,e.w,e.d]); });
function dijkstra(src,dst){
  const dist={},prev={}; Object.keys(ADJ).forEach(k=>dist[k]=Infinity); dist[src]=0;
  const pq=new Set(Object.keys(ADJ));
  while(pq.size){ let u=null,b=Infinity; pq.forEach(n=>{ if(dist[n]<b){b=dist[n];u=n;} });
    if(u===null||u===dst) break; pq.delete(u);
    ADJ[u].forEach(([v,w])=>{ if(pq.has(v)&&dist[u]+w<dist[v]){ dist[v]=dist[u]+w; prev[v]=u; } }); }
  if(dist[dst]===Infinity) return null;
  const path=[]; let c=dst; while(c!==undefined){ path.unshift(c); if(c===src)break; c=prev[c]; }
  return {path,cost:dist[dst]};
}
window.rmap=null; let rLayer=null;
function initRouting(){
  const froms=document.getElementById('r-from'), tos=document.getElementById('r-to');
  const sts=meta.nodes.filter(n=>n.type==='JUNCTION').slice().sort((a,b)=>a.name.localeCompare(b.name));
  const opts=sts.map(n=>`<option value="${n.id}">${n.name}</option>`).join('');
  froms.innerHTML=opts; tos.innerHTML=opts; froms.value=sts[0].id; tos.value=sts[Math.min(sts.length-1,15)].id;
  rmap=L.map('rmap',{scrollWheelZoom:false});
  baseLayer().addTo(rmap);
  rmap.fitBounds(L.latLngBounds(Object.values(LL).filter(Boolean)).pad(0.06));
  meta.links.forEach(l=>{ const g=segGeom(l.s,l.t); if(g) L.polyline(g,{color:l.color||'#9aa0a6',weight:l.line==='Service'?1.5:2.5,opacity:.35}).addTo(rmap); });
  rLayer=L.layerGroup().addTo(rmap);
  document.getElementById('r-go').onclick=computeRoute;
  setTimeout(()=>{ rmap.invalidateSize(); computeRoute(); },60);
}
function computeRoute(){
  const s=document.getElementById('r-from').value, d=document.getElementById('r-to').value;
  const out=document.getElementById('r-out'), pl=document.getElementById('r-path'); rLayer.clearLayers();
  if(s===d){ out.innerHTML='<span class="text-on-surface-variant">Origin and destination are the same.</span>'; pl.innerHTML=''; return; }
  const res=dijkstra(s,d);
  if(!res){ out.innerHTML='<span class="text-error">No path found.</span>'; pl.innerHTML=''; return; }
  let dist=0; for(let k=1;k<res.path.length;k++){ const e=(ADJ[res.path[k-1]]||[]).find(x=>x[0]===res.path[k]); if(e) dist+=e[2]; }
  out.innerHTML=`<div class="p-3 rounded-lg bg-surface-container-low">${res.path.length-1} hops &middot; <b>${dist.toFixed(1)} km</b> &middot; ETA <b>${round(res.cost*60)} min</b><br><span class="text-xs text-on-surface-variant">minimised by Dijkstra (free-flow travel time)</span></div>`;
  pl.innerHTML=res.path.map((id,k)=>`<li class="flex items-center gap-2 px-2 py-1 ${k===0?'font-bold text-primary':k===res.path.length-1?'font-bold text-error':''}">
    <span class="material-symbols-outlined text-sm">${k===0?'trip_origin':k===res.path.length-1?'place':'fiber_manual_record'}</span>${NAME[id]||id}</li>`).join('');
  const geo=routeGeom(res.path); const pts=geo.length?geo:res.path.map(id=>LL[id]).filter(Boolean);
  rLayer.addLayer(L.polyline(pts,{color:'#006948',weight:6,opacity:.9}));
  rLayer.addLayer(L.circleMarker(LL[s],{radius:8,color:'#006948',fillColor:'#85f8c4',fillOpacity:1}));
  rLayer.addLayer(L.circleMarker(LL[d],{radius:8,color:'#ba1a1a',fillColor:'#ffdad6',fillOpacity:1}));
  rmap.fitBounds(L.latLngBounds(pts).pad(0.25));
}

document.querySelectorAll('[data-view]').forEach(a=>a.addEventListener('click',e=>{ e.preventDefault(); showView(a.getAttribute('data-view')); location.hash=a.getAttribute('data-view'); }));
const _hv=(location.hash||'').replace('#','');
showView(['control','fleet','metro','routing','health'].includes(_hv)?_hv:'control');
</script>
</body></html>
"""


def build_html(ticks: int, seed: int, topology: str) -> str:
    engine = SimulationEngine(seed=seed, verbose=False, topology=topology)
    engine.run_ticks(ticks)
    payload = {"meta": engine.viz_meta(), "frames": engine.frames, "latlng": CORE_LATLNG}
    url, opts = tile_config()
    return (_TEMPLATE.replace("__DATA__", json.dumps(payload))
            .replace("__TILE_URL__", url).replace("__TILE_OPTS__", opts))


def main() -> None:
    p = argparse.ArgumentParser(description="Generate the EcoShield Delhi dashboard.")
    p.add_argument("--ticks", type=int, default=40)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--topology", choices=["metro", "core"], default="metro")
    p.add_argument("--out", default="dashboard.html")
    p.add_argument("--open", action="store_true")
    args = p.parse_args()
    html = build_html(args.ticks, args.seed, args.topology)
    out = os.path.abspath(args.out)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Wrote {out}  ({len(html)//1024} KB, {args.ticks} ticks, {args.topology} topology)")
    print(f"  open '{out}'")
    if args.open:
        webbrowser.open("file://" + out)


if __name__ == "__main__":
    main()
