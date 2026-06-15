# EcoShield Delhi — Agentic AI Pollution-Control System

A decentralised fleet of anti-smog **water-sprinkler tankers** and dedicated
**road-cleaning trucks**, routed across the **Delhi Metro network** by a central
AI coordinator running a **modified, multi-objective Dijkstra** solver. The
coordinator predicts PM2.5 spikes, splits work across coordinated sub-fleets,
handles real-time "stuck in traffic" exceptions, and keeps every truck fuelled
and watered through a closed supply loop — autonomously, with no human in the
routing decision.

- **Live dashboard:** https://krishiv47.github.io/ecoshield-delhi-ai/
- **Driver console:** https://krishiv47.github.io/ecoshield-delhi-ai/driver.html
- **Source:** https://github.com/krishiv47/ecoshield-delhi-ai
- **Presentation:** [EcoShield-Delhi.pptx](EcoShield-Delhi.pptx) · [EcoShield-Delhi.pdf](EcoShield-Delhi.pdf) · [presentation.html](presentation.html)
- **Screenshots:** [`screenshots/`](screenshots)

> Pure **Python 3.10+, standard library only** for the engine; a keyless,
> build-step-free **Leaflet** front end. Runs unchanged on Python 3.9 via
> `from __future__ import annotations`.

---

## Highlights

- **Two coordinated fleets** — 16 anti-smog sprinkler tankers (Mini 3000 L /
  Medium 5000 L / Heavy 12000 L) that mist hotspots, plus **10 dedicated
  road-cleaning trucks** that continuously wet-wash roads to bind settled dust so
  it stays on the ground instead of being resuspended as PM10 / PM2.5.
- **Real Delhi Metro graph** — ~50 stations across all 8 lines + 6 water/charging
  depots (134 directed edges), with every edge snapped to **real road geometry**
  (OSRM) so trucks, routes and metro lines follow actual streets.
- **Modified multi-objective Dijkstra** — vehicle-aware, congestion- and
  emission-weighted shortest paths, recomputed from live telemetry.
- **Continuous simulation** — procedurally generated hotspots keep the network
  active indefinitely; the dashboard auto-plays and loops.
- **Operations dashboard** (single-page app) with five working views, a real map,
  and an animated timeline.
- **Restricted driver console** — a bounded in-cab terminal; admins can open any
  driver, drivers cannot reach admin modules.
- **28 passing tests**, deployed live on GitHub Pages.

---

## Quick start

```bash
# Console simulation (text dashboard each tick)
python3 main.py                 # 16-tick showcase
python3 main.py --quiet         # intro + final summary only

# Tests
python3 -m unittest discover -s tests -t . -v     # 28 tests

# Browser UIs (generate + open)
python3 dashboard.py --open                 # admin dashboard, Delhi Metro map (default)
python3 dashboard.py --topology core --open # original 6-junction map
python3 driver.py --open                    # restricted driver console (busiest unit)
python3 driver.py --truck RC-03 --open      # a specific unit (e.g. a road cleaner)
python3 visualize.py --open                 # lightweight SVG network player

# Presentation
node build_pptx.js              # -> EcoShield-Delhi.pptx (needs: npm install pptxgenjs)

# Refresh road geometry cache (optional, needs network)
python3 build_geometry.py       # -> smog_control/edge_geometry.json (OSRM)
```

No third-party runtime dependencies for the simulation. `dashboard.py` /
`driver.py` only need the standard library; `build_pptx.js` needs `pptxgenjs`.

---

## Domain & mathematical model

### Network graph `G = (V, E)`

- **Nodes (V):** metro stations with dynamic `current_AQI_PM25` and
  `traffic_rate_influx` plus rolling history for trend analytics.
- **Special nodes:** `SewageTreatmentPlantNode` (recycled water) and
  `RefuelingStationNode` (CNG/EV), unified under a `ServiceNode` abstract base.
- **Edges (E):** stateful road segments whose `traffic_density_factor` and
  `emission_penalty` mutate every tick, each carrying a real-road polyline.

### Dynamic, multi-objective edge cost

```
W(e, vehicle) = ( distance_km / base_speed ) x traffic_density_factor   (congestion-stretched travel time)
              + emission_penalty(e, vehicle)                            (idling-emission overhead)

emission_penalty = COEF x emission_weight(vehicle) x traffic_factor x severity
                   # only when a heavy chassis idles into an already-critical cell
```

Because the penalty depends on the vehicle, two tankers can receive two different
optimal paths over the same graph at the same instant — the defining property of
the *modified* router. The solver is a binary-heap single-source Dijkstra,
`O((V+E) log V)`, used both in Python and (for the Routing Engine view) in the
browser.

---

## Agents

### Central AI Coordinator (`smog_control/coordinator.py`)

- **State** — global telemetry of the graph and the full fleet.
- **Predictive analytics** — a >40% rise in an edge's congestion over two ticks
  flags an imminent breach *before* the sensor reflects it.
- **Dispatcher** — an Efficiency-Score Matrix selects a 2–3 truck sub-fleet and
  staggers arrivals so each tanker rolls in as the previous empties.
- **Exceptions & supply** — handles the stuck-in-traffic branches and the closed
  supply loop (below).
- **Road-cleaning control** — sends the cleaner fleet on continuous patrols of the
  dustiest corridors and applies dust suppression as they wash.

### Tanker trucks (`smog_control/trucks.py`)

Dumb kinematic actuators with the full required state (`truck_id`,
`capacity_class`, `current_node`, `target_node`, `water_level_liters`,
`fuel_energy_pct`, `current_speed_kmh`, `operational_status`). A `role` field
distinguishes `SPRINKLER` (hotspot misting) from `CLEANER` (road washing). Drivers
steer; the AI dictates the route.

---

## Workflows (every tick)

1. **Sense** — ingest live PM2.5 and traffic from every node and edge.
2. **Predict** — flag imminent breaches from accelerating traffic.
3. **Dispatch** — score, select and ETA-synchronise a sprinkler sub-fleet per hotspot.
4. **Route** — modified Dijkstra computes each truck's path.
5. **Mitigate** — sprinklers mist hotspots; road cleaners wash streets and bind dust.
6. **Adapt — stuck in traffic:**
   - *In-hotspot trapped* → engage a **stationary misting curtain** in place.
   - *En-route interception* → revoke target, lock the console, mark `STUCK`,
     recompute the graph, and **re-allocate** the load to an unblocked unit.
7. **Replenish — closed loop:** below 15% water / 20% fuel the AI locks the in-cab
   console, routes to the lowest-weight STP / refuelling node, mocks a fast-pass
   micro-transaction, and reintegrates the truck at ≥95%.
8. **Repeat** — continuously, with a resting reserve always on standby.

---

## The dashboard (`dashboard.py` → `index.html`)

A single-page app on the *Ecologic Intelligence System* design language (Tailwind
+ Inter, emerald/indigo, **no emojis**), over a real Leaflet/CARTO map. Every
sidebar item opens a real, data-driven view:

- **Admin Control** — live map overview (stat cards, hotspots, fleet, event stream).
- **Fleet Operations** — live roster of all trucks; click a row to open that
  driver's console.
- **Metro Network** — live station air-quality table across all lines.
- **Routing Engine** — interactive **Dijkstra** path finder (origin → destination,
  drawn along real roads with hops / km / ETA).
- **System Health** — live platform & coordinator telemetry.

On the map: sprinkler tankers are circles (**filled = misting, hollow = resting**),
road cleaners are **teal squares**, metro lines use their official colours, and
gridlock is highlighted live. Maps are isolated into their own stacking contexts so
overlays never bleed over the header. Set `MAPPLS_KEY` in `dashboard.py` to switch
the basemap to Mappls / MapmyIndia.

## The driver console (`driver.py` → `driver.html`)

A deliberately **restricted** role view. The five admin modules are shown locked
("access restricted to Fleet Commander"). The console follows one unit and shows
its AI-assigned Dijkstra route over the metro map, current mission, water/charge
gauges and the live AI instruction feed. The admin can deep-link to any unit via
`driver.html?truck=WT-07` (or `RC-03` for a road cleaner); drivers cannot reach
admin modules.

---

## Project structure

```
smog_control/
  config.py        tunable constants (units documented inline)
  enums.py         OperationalStatus, CapacityClass, NodeType, AQICategory
  topology.py      Node (+ ServiceNode/STP/Refuel), Edge, TransitGraph
  metro.py         Delhi Metro stations, lines, depots, fleet, scenario
  routing.py       MultiObjectiveRouter (modified Dijkstra) + Route
  trucks.py        TankerTruck agent (SPRINKLER / CLEANER), Telemetry
  dispatch.py      FleetDispatcher: efficiency matrix, splitting, ETA sync
  coordinator.py   CentralAICoordinator: prediction, dispatch, exceptions, supply, road cleaning
  engine.py        SimulationEngine: world, dynamics, incident director, dashboard, frame export
  edge_geometry.json   cached OSRM road polylines per edge
main.py            console runner
dashboard.py       admin dashboard generator (index.html)
driver.py          driver console generator (driver.html)
visualize.py       lightweight SVG player (simulation.html)
build_pptx.js      native PowerPoint generator (EcoShield-Delhi.pptx)
build_geometry.py  one-off OSRM road-geometry fetch
tests/             28 unit + integration tests
presentation.html  13-slide HTML deck (-> EcoShield-Delhi.pdf)
```

---

## Deployment

The repo is published to GitHub Pages (branch `main`, root). `index.html` is the
deployed admin dashboard; it runs a pre-computed, continuously-looping simulation
entirely client-side, so the live link is always on with no server. Pushing to
`main` auto-redeploys.

---

## Notes & roadmap

- Road shapes are OSRM **driving** routes between stations (real roads) — exactly
  right for water trucks; they approximate, not exactly trace, the underground
  metro alignment.
- The station set is a curated backbone of major stations and interchanges across
  all lines; extend it by adding rows to `smog_control/metro.py`.
- Roadmap: live IoT AQI + traffic feeds, Mappls basemap + turn-by-turn directions,
  GTFS metro alignments, and reinforcement-learned dispatch. The architecture is
  data-source agnostic — swapping the simulated feed for real telemetry needs no
  change to the agents or the solver.
