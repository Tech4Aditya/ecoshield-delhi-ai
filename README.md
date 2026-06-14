# Agentic AI Pollution-Control System — Delhi Anti-Smog Tanker Network

**Live demo:** https://krishiv47.github.io/ecoshield-delhi-ai/ — the continuously-running
EcoShield admin dashboard (live Leaflet map of the Delhi Metro, moving fleet, Fleet /
Metro / Routing / Health views).
**Driver console:** https://krishiv47.github.io/ecoshield-delhi-ai/driver.html

A production-grade, single-process **multi-agent simulation** in which a
**Central AI Coordinator** orchestrates a decentralised fleet of IoT-equipped
water-tanker trucks (mobile anti-smog misting cannons) across Delhi's transit
topology, routing them with a **modified, dynamic, multi-objective Dijkstra**
solver to suppress PM2.5 hotspots in real time.

The system models — and *natively handles* — predictive spike pre-emption,
coordinated multi-truck workload splitting with staggered arrivals, both
"stuck-in-traffic" exception branches, and a fully autonomous closed-loop
water/fuel replenishment lifecycle.

```
python3 main.py                 # default 16-tick showcase scenario (seed 7)
python3 main.py --ticks 24      # run longer
python3 main.py --seed 42       # different background-noise stream
python3 main.py --quiet         # intro + final summary only (no per-tick dashboard)
python3 -m unittest discover -s tests -t . -v   # run the 28-test suite

python3 visualize.py --open     # lightweight SVG network player (simulation.html)

python3 dashboard.py --open                 # EcoShield ops dashboard, Delhi Metro map (default)
python3 dashboard.py --topology core --open # original 6-junction map
python3 dashboard.py --ticks 24 --seed 42   # customise the visualised run
```

### EcoShield dashboard (`dashboard.py`)

A production-style operations console built on the *Ecologic Intelligence System*
design language (Tailwind + Inter + Material Symbols, emerald/indigo — no emojis).
The default `metro` build runs the simulation over **~50 real Delhi Metro stations
across all lines** plus 6 water/charging depots, rendered on a real Leaflet map of
Delhi (detailed keyless CARTO Voyager street basemap; set `MAPPLS_KEY` in
`dashboard.py` to switch every map to Mappls/MapmyIndia tiles):

* Metro **lines drawn in their official colors**; stations as PM2.5 heat zones.
* Water-sprinkler tankers that either **CLEAN** hotspots (spraying / en-route,
  shown filled) or **REST** in reserve at depots (shown hollow), with live
  cleaning-vs-resting counts.
* Animated timeline (play / scrub / speed), live stat cards, critical-hotspot
  list, agentic-fleet panel and the AI coordinator event stream.

Every sidebar item opens a real, data-driven view (single-page app):

* **Admin Control** — the live map overview.
* **Fleet Operations** — live roster of all tankers; click a row to open that
  driver's console.
* **Metro Network** — live station air-quality table across all lines, sorted by
  PM2.5, with healthy/poor/severe counts.
* **Routing Engine** — interactive **Dijkstra** path finder: pick origin +
  destination, it minimises free-flow travel time over the 134-edge directed
  graph and draws the optimal path on a map (hops, km, ETA).
* **System Health** — live platform/coordinator telemetry (topology size, fleet
  status breakdown, subsystem status).

Topology is selectable in code via `SimulationEngine(topology="metro"|"core")`.
Playback runs **continuously** — the metro scenario procedurally spawns fresh
hotspots on a rolling cadence, and the dashboard auto-plays and loops, so tankers
keep cycling between cleaning duty and the resting reserve indefinitely.

### Driver console (`driver.py`)

```
python3 driver.py --open                 # follow the busiest tanker
python3 driver.py --truck WT-13 --open   # follow a specific unit
```

A deliberately **restricted role view** — the driver is a bounded actuator. The
admin modules (Admin Control, Fleet Operations, Metro Network, Routing Engine,
System Health) are shown **locked** (a lock icon + an "access restricted to Fleet
Commander" notice on click). The console follows one tanker and shows its
AI-assigned, **Dijkstra-optimised route** over the metro map (full path + remaining
legs + next stop + km left), the current mission, water/charge gauges, and the
live AI instruction feed. When the Central AI overrides the in-cab console
(replenishment or active mission) a "console locked" banner appears — the human
steers, but the AI dictates.

**Role hierarchy (one-way).** Drivers cannot reach admin modules, but the admin
*can* open any driver portal: the dashboard links to it from the sidebar, a
top-bar "Driver Portal" switcher, a map button, and — most usefully — **clicking
any tanker on the map opens that unit's console** (`driver.html?truck=WT-07`).
The driver portal embeds every unit and selects by the `?truck=` query param.

> **Runtime.** Written to **Python 3.10+** standards (PEP 604 annotations,
> modern generics, dataclasses) using **only the standard library**
> (`heapq`, `collections`, `enum`, `dataclasses`, `abc`-style ABCs via
> subclassing, `random`, `math`, `typing`, `argparse`, `unittest`). It is also
> forward/backward-compatible down to **3.9** via `from __future__ import
> annotations`, so it runs unchanged on stock macOS Python.

---

## 1. Domain & Mathematical Framework

### A. Network topology graph `G = (V, E)`

A **directed** graph (`smog_control/topology.py`). Six mandated core junctions
plus four supply-infrastructure vertices:

| id | Node | Role | Character |
|----|------|------|-----------|
| `AV` | Anand Vihar | Junction | Interstate hub (remote, east) |
| `ITO` | ITO | Junction | High-density commercial |
| `CP` | Connaught Place | Junction | Central core |
| `DWK` | Dwarka | Junction | Suburban residential (west) |
| `PRG` | Peeragarhi | Junction | Industrial / transit bottleneck |
| `AIIMS` | AIIMS | Junction | Medical / high-volume intersection |
| `OKH` | Okhla STP | **`SewageTreatmentPlantNode`** | Recycled-water source |
| `NJF` | Najafgarh STP | **`SewageTreatmentPlantNode`** | Recycled-water source |
| `ROH` | Rohini CNG Hub | **`RefuelingStationNode`** | CNG / EV charging |
| `DCG` | Dwarka CNG/EV | **`RefuelingStationNode`** | CNG / EV charging |

Every node tracks **dynamic** `current_AQI_PM25` and `traffic_rate_influx`,
plus rolling history buffers (`deque`) for trend analytics and planar `(x, y)`
coordinates used by the localised-hotspot geometry test. The two special
subclasses model the closed-loop supply economy (finite recycled-water
reservoir; per-minute pumping / charging rates).

The graph is a **redundant mesh** — every junction has multiple disjoint paths —
so the router always has an *unblocked perimeter bypass* to re-allocate onto
during en-route interception.

### B. Dynamic multi-objective edge cost `W(e)`

Each edge (`Edge`) is **stateful**: its `traffic_density_factor` (1.0 free-flow
→ up to 12.0 total blockage) and `emission_penalty` mutate every tick. The
weight used by the router is:

```
            distance_km
W(e) =  ( ───────────── · traffic_density_factor )  +  emission_penalty(e, vehicle)
             base_speed
        └──────── congestion-stretched travel time (h) ──┘   └─ AI idling overhead ─┘
```

* **Term 1** is free-flow travel time stretched by live congestion.
  `effective_speed = base_speed / traffic_density_factor`, so a factor of 12 on a
  42 km/h arterial yields 3.5 km/h — below the 5 km/h *stuck* threshold.
* **Term 2** (`MultiObjectiveRouter.emission_penalty`) is the dynamic overhead
  the Central AI levies to optimise **secondary fleet emissions**. It is
  non-zero *only* when a vehicle would **idle** (`traffic_factor ≥ 2.5`) while
  crossing into an **already-critical** cell:

  ```
  severity = max(0, (AQI_dest − CRITICAL_PM25) / CRITICAL_PM25)
  penalty  = COEF · emission_weight(vehicle) · traffic_factor · severity
  ```

  `emission_weight` is `1.0 / 1.6 / 2.5` for Mini / Medium / Heavy — so the
  same graph yields **different optimal paths for different chassis** at the
  same instant. This is what makes the router *modified* rather than vanilla
  Dijkstra. The implementation runs a binary-heap single-source Dijkstra in
  `O((V+E) log V)` and decomposes the result into travel-time, distance and
  emission components.

### C. Air-quality dynamics

Per tick, every junction accrues pollution and spraying knocks it down:

```
ΔAQI_accrual = AMBIENT_DRIFT + INFLUX_COEF · traffic_rate_influx     (rise)
ΔAQI_spray   = litres_atomised · SPRAY_AQI_PER_LITRE                 (fall)
```

A cell becomes an **actionable hotspot** at `AQI ≥ 250` (CPCB Very-Poor/Severe
border) and a mission is **resolved** once it falls below `185`.

---

## 2. Architecture & Agents

Strict OOD; clean dependency DAG (no cycles):

```
config ─► enums ─► topology ─► routing ─► dispatch ─► coordinator ─► engine ─► main
                         └────────► trucks ─────────────┘
```

| Module | Responsibility |
|--------|----------------|
| `config.py` | All tunable constants (units documented inline) |
| `enums.py` | `OperationalStatus`, `CapacityClass`, `NodeType`, `AQICategory` |
| `topology.py` | `Node` (+ `SewageTreatmentPlantNode`, `RefuelingStationNode`), `Edge`, `TransitGraph` |
| `routing.py` | `MultiObjectiveRouter`, `Route` — the modified Dijkstra |
| `trucks.py` | `TankerTruck` agent, kinematics, `Telemetry`, `MoveResult` |
| `dispatch.py` | `FleetDispatcher` — efficiency matrix, sub-fleet selection, ETA sync |
| `coordinator.py` | `CentralAICoordinator` — prediction, dispatch, exceptions, supply loop |
| `engine.py` | `SimulationEngine` — world build, dynamics, incident director, dashboard |

### Agent 1 — Central AI Coordinator (`coordinator.py`)

* **State management.** Owns the graph, the full fleet, and a per-truck
  `Telemetry` store refreshed every tick.
* **Predictive analytics — `run_prediction()`.** Differentiates each edge's
  congestion factor across two ticks; a rise `> 40 %` on a corridor whose
  destination cell is already trending toward critical flags an **imminent
  breach before the physical sensor reflects it**, triggering a *pre-emptive
  curtain*.
* **Global fleet dispatcher — `run_dispatch()`.** Opens/escalates missions and
  invokes the coordinated multi-agent assignment solver.

### Agent 2 — Mobile Tanker Trucks (`trucks.py`)

Carry every attribute from the brief — `truck_id`, `capacity_class`
(Mini 3000 L / Medium 5000 L / Heavy 12000 L), `current_node`, `target_node`,
`water_level_liters`, `fuel_energy_pct`, `current_speed_kmh`,
`operational_status` (`IDLE`/`EN_ROUTE`/`SPRAYING`/`STUCK`/`REPLENISHING`) — and
push a `Telemetry` snapshot upward each tick. Trucks are **dumb actuators**:
movement is deterministic given graph state; only the AI commands them.

---

## 3. Workflow Logic & Algorithmic Constraints

### A. Multi-truck ETA synchronisation & workload splitting (`dispatch.py`)

When a hotspot needs volume `V_req = max(2500, (AQI − 250) · 60)` litres, the
dispatcher does **not** grab the single nearest truck. It:

1. **Efficiency-Score Matrix** — scores every in-radius, available, fuel-viable
   tanker:
   ```
   score = W_VOLUME·min(1, deliverable/V_req)        (coverage)
         + W_ETA·1/(1 + eta_min/30)                  (responsiveness)
         + W_FUEL·(fuel_pct/100)                      (energy margin)
         + W_CLASS·min(1, capacity/V_req)             (sizing fit)
   ```
2. **Sub-fleet selection** — greedily takes the smallest high-scoring set
   (≤ 3 tankers) whose combined water covers `V_req`.
3. **ETA synchronisation** — staggers departures via per-truck *loiter gates* so
   each tanker arrives as the previous one empties:
   ```
   arrival[0]  = now + eta_ticks[0]
   finish[k-1] = arrival[k-1] + spray_ticks[k-1]
   hold[k]     = max(now, finish[k-1] − eta_ticks[k])
   ```
   producing a **continuous mitigation curtain** instead of a convoy that all
   arrives and empties at once. (See a truck in `ETA-sync loiter` status in the
   dashboard.)

### B. Real-time "stuck in traffic" exception logic (`coordinator.process_movement`)

When an assigned truck's `current_speed_kmh` drops below **5 km/h**:

1. **In-hotspot trapped** → if the truck is *inside the localised coordinates of
   its target zone* (Euclidean test against the node radius), it engages its
   **stationary misting curtain** in place (reduced 0.6 efficiency, pitch-
   adjusted) to knock down surrounding idling exhaust. It keeps the mission.
2. **En-route interception** → if trapped *far from* its hotspot, the AI
   **revokes the target, locks the driver console, sets status `STUCK`**, and
   immediately **re-allocates the revoked workload** to the best unblocked unit,
   whose route is freshly recomputed on the post-incident graph (inherently
   avoiding the gridlock). Stuck units auto-recover to the pool once their
   segment clears.

> A small **incident director** in the engine injects one gridlock onto the
> exact segment a mission truck occupies, so both branches fire on *real* routes
> regardless of which trucks the dispatcher happened to pick — making the
> showcase deterministic.

### C. Autonomous closed-loop supply lifecycle (`coordinator.run_supply_lifecycle`)

> *"The human steers, but the AI dictates."*

* When `water < 15 %` **or** `fuel < 20 %`, the AI **interrupts the current
  track** (idle, spraying, or even mid-mission), **locks the in-cab console**,
  and runs a Dijkstra command to the **lowest-weight STP / refuelling node**.
* It **pre-authorises the gate** and issues a mocked **fast-pass
  micro-transaction** token on arrival.
* Once the fluid/charge level reaches **≥ 95 %**, the truck is **automatically
  reintegrated** into the available fleet queue, and the released mission share
  is naturally topped-up by the next dispatch pass.

---

## 4. The per-tick pipeline

```
begin_tick → update_environment(+incident director) → ingest_telemetry
→ run_prediction → run_dispatch → advance_fleet → process_movement (arrivals/STUCK)
→ run_spraying → run_supply_lifecycle → recover_stuck → close_missions → render_dashboard
```

Each tick prints a structured console dashboard: scenario/incident banners, the
**AI coordinator event log**, the **network/AQI state** table, **fleet
telemetry**, and **congestion hotspots**.

---

## 5. What the default run demonstrates

| Tick(s) | Workflow exercised |
|---------|--------------------|
| 1 | Low-fuel truck (T4) → autonomous **refuel** lifecycle |
| 2 | Severe AIIMS spike → **multi-truck split + ETA-sync** loiter |
| 4 | **In-hotspot stationary misting** (T1 boxed in at AIIMS) |
| 4 | **Predictive** pre-emptive curtain for Anand Vihar |
| 5 | **En-route interception** (T4 gridlocked) → re-allocation to T8 |
| 5–7 | **Water replenishment** lifecycle (emptied tankers → STP) |
| 6 | **Stuck recovery**; AIIMS mission **resolved** |
| 7+ | Second wave (ITO) handled; Peeragarhi & ITO **resolved** |

---

## 6. Extensibility

* **New cost objectives** — add a term to `MultiObjectiveRouter.edge_weight`.
* **New node behaviours** — subclass `Node` (mirror the STP/Refuel pattern).
* **New scenarios** — edit `SimulationEngine._build_scenario` (declarative event
  grammar) or the `_dynamic_events` incident director.
* **Real telemetry** — replace `_update_environment` with a live IoT feed; the
  agents and solver are agnostic to the data source.
