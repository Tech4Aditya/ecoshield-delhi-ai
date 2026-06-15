"""
Simulation engine: world-building, physics integration and the console dashboard.

``SimulationEngine`` wires the topology, the fleet and the Central AI Coordinator
together and drives the canonical per-tick pipeline:

    environment update -> telemetry -> prediction -> dispatch -> movement
    -> exception reconciliation -> spraying -> supply lifecycle
    -> stuck recovery -> mission closure -> dashboard render

A small scripted-events table injects the shocks (severe AQI spikes, congestion
surges, gridlock) needed to exercise every workflow branch deterministically,
layered on top of mean-reverting stochastic background dynamics.
"""

from __future__ import annotations

import json
import random
from typing import Optional

from .config import TICK_MINUTES, TRAFFIC_FACTOR_MAX
from .coordinator import CentralAICoordinator
from .dispatch import FleetDispatcher
from .enums import CapacityClass, NodeType, OperationalStatus
from .routing import MultiObjectiveRouter
from .topology import (
    Edge,
    Node,
    RefuelingStationNode,
    SewageTreatmentPlantNode,
    TransitGraph,
)
from .trucks import MoveResult, TankerTruck

# Display ordering / widths for the dashboard.
_LINE = "=" * 96
_SUB = "-" * 96


class SimulationEngine:
    """Top-level orchestrator and renderer for the smog-control simulation."""

    def __init__(self, seed: int = 7, verbose: bool = True, topology: str = "core") -> None:
        self.rng = random.Random(seed)
        self.verbose = verbose
        self.topology = topology

        if topology == "metro":
            from .metro import build_metro_fleet, build_metro_graph, metro_scenario
            self.graph: TransitGraph = build_metro_graph()
            self.fleet: list[TankerTruck] = build_metro_fleet(self.graph)
            self.scenario = metro_scenario()
        else:
            self.graph = self._build_delhi_topology()
            self.fleet = self._spawn_fleet()
            self.scenario = self._build_scenario()

        self.router = MultiObjectiveRouter(self.graph)
        self.dispatcher = FleetDispatcher(self.router)
        self.coordinator = CentralAICoordinator(
            self.graph, self.fleet, self.router, self.dispatcher
        )

        # Baselines for mean-reverting background dynamics.
        self._influx_base = {n.node_id: n.traffic_rate_influx for n in self.graph.nodes()}
        self._factor_base = {e.key: e.traffic_density_factor for e in self.graph.edges()}

        # Live "incident director": injects a single gridlock onto whatever
        # segment an active mission truck happens to occupy, so both stuck-in-
        # traffic branches fire on real routes regardless of dispatcher choices.
        self._director = {"interception_done": False, "inhotspot_done": False}
        self._incident_banner = ""

        # Per-tick state frames captured for the browser visualiser.
        self.frames: list[dict] = []

    # ================================================================== #
    # World construction                                                  #
    # ================================================================== #
    def _build_delhi_topology(self) -> TransitGraph:
        """Construct the directed transit graph of Delhi's key junctions.

        Six mandated core junctions plus four supply-infrastructure vertices
        (two STPs, two CNG/charging stations), connected into a redundant mesh
        so the router always has alternative perimeter bypasses to re-allocate
        onto during en-route interception events.
        """
        g = TransitGraph()

        # --- Core junctions (id, name, x, y, AQI0, influx0, radius) ------- #
        g.add_node(Node("AV", "Anand Vihar", 24, 8, current_AQI_PM25=120, traffic_rate_influx=1.5, radius_km=2.5))
        g.add_node(Node("ITO", "ITO", 14, 6, current_AQI_PM25=140, traffic_rate_influx=1.7, radius_km=2.5))
        g.add_node(Node("CP", "Connaught Place", 11, 7, current_AQI_PM25=115, traffic_rate_influx=1.4, radius_km=2.2))
        g.add_node(Node("DWK", "Dwarka", 2, 1, current_AQI_PM25=85, traffic_rate_influx=1.0, radius_km=2.0))
        g.add_node(Node("PRG", "Peeragarhi", 4, 11, current_AQI_PM25=150, traffic_rate_influx=1.6, radius_km=2.5))
        g.add_node(Node("AIIMS", "AIIMS", 10, 2, current_AQI_PM25=105, traffic_rate_influx=1.3, radius_km=2.6))

        # --- Supply infrastructure --------------------------------------- #
        g.add_node(SewageTreatmentPlantNode("OKH", "Okhla STP", 16, 0, current_AQI_PM25=90, traffic_rate_influx=0.8))
        g.add_node(SewageTreatmentPlantNode("NJF", "Najafgarh STP", 1, 5, current_AQI_PM25=80, traffic_rate_influx=0.7))
        g.add_node(RefuelingStationNode("ROH", "Rohini CNG Hub", 6, 16, current_AQI_PM25=95, traffic_rate_influx=0.7, fuel_kind="CNG"))
        g.add_node(RefuelingStationNode("DCG", "Dwarka CNG/EV", 4, 1, current_AQI_PM25=82, traffic_rate_influx=0.6, fuel_kind="CNG+EV"))

        # --- Road segments: Edge(u, v, distance_km, base_speed, factor) --- #
        def link(u: str, v: str, km: float, speed: float, factor: float = 1.3) -> None:
            g.add_edge(Edge(u, v, km, speed, traffic_density_factor=factor), bidirectional=True)

        # Inner arterials.
        link("CP", "ITO", 6, 40, 1.6)
        link("CP", "AIIMS", 7, 30, 1.5)          # deliberately lower design speed
        link("ITO", "AIIMS", 8, 38, 1.6)
        link("ITO", "AV", 11, 45, 1.5)
        # Cross-city / bottleneck corridors.
        link("ITO", "PRG", 16, 28, 1.8)          # the industrial bottleneck corridor
        link("CP", "PRG", 15, 35, 1.5)           # alternative bypass
        link("AIIMS", "PRG", 17, 38, 1.4)        # alternative bypass
        link("AIIMS", "DWK", 16, 50, 1.2)
        link("DWK", "PRG", 18, 42, 1.3)
        # Outer ring road (fast perimeter bypass).
        link("PRG", "AV", 24, 55, 1.2)
        # Infrastructure spurs.
        link("ITO", "OKH", 9, 40, 1.3)
        link("AIIMS", "OKH", 8, 42, 1.3)
        link("AIIMS", "NJF", 14, 45, 1.2)
        link("DWK", "NJF", 6, 40, 1.2)
        link("DWK", "DCG", 3, 40, 1.1)
        link("PRG", "ROH", 9, 40, 1.2)
        link("AV", "ROH", 20, 50, 1.2)

        return g

    def _spawn_fleet(self) -> list[TankerTruck]:
        """Instantiate a heterogeneous fleet positioned across the network.

        Two units start pre-stressed (T4 low fuel, demonstrating the refuel
        lifecycle; the heavy units will drain water during the severe-spike
        campaign, demonstrating the STP lifecycle).
        """
        H, M, Mini = CapacityClass.HEAVY, CapacityClass.MEDIUM, CapacityClass.MINI
        fleet = [
            TankerTruck("T1", H, "CP", water_level_liters=H.litres, fuel_energy_pct=100),
            TankerTruck("T2", M, "ITO", water_level_liters=M.litres, fuel_energy_pct=95),
            TankerTruck("T3", Mini, "AIIMS", water_level_liters=Mini.litres, fuel_energy_pct=90),
            TankerTruck("T4", H, "DWK", water_level_liters=H.litres, fuel_energy_pct=18),
            TankerTruck("T5", M, "AV", water_level_liters=M.litres, fuel_energy_pct=88),
            TankerTruck("T6", Mini, "ITO", water_level_liters=Mini.litres, fuel_energy_pct=82),
            TankerTruck("T7", H, "CP", water_level_liters=H.litres, fuel_energy_pct=92),
            TankerTruck("T8", M, "AIIMS", water_level_liters=M.litres, fuel_energy_pct=86),
        ]
        for truck in fleet:
            truck.sync_position(self.graph)
        return fleet

    # ================================================================== #
    # Scripted scenario                                                   #
    # ================================================================== #
    def _build_scenario(self) -> dict:
        """Tick-indexed shocks that deterministically exercise each workflow.

        Event grammar (applied *after* background dynamics each tick):
            ("aqi",   node_id, value)        -> set absolute PM2.5
            ("influx",node_id, value)        -> set absolute influx index
            ("factor",u, v,    value)        -> set directed edge congestion
            ("banner",text)                  -> scenario annotation
        """
        return {
            1: [("banner", "Nominal morning operations; fleet idle & topped-up.")],
            2: [
                ("banner", "SEVERE crop-burning + inversion spike over AIIMS."),
                ("aqi", "AIIMS", 475.0),
                ("influx", "AIIMS", 2.6),
            ],
            3: [
                ("banner", "Traffic building on the ITO->Anand Vihar arterial."),
                ("factor", "ITO", "AV", 2.0),
                ("influx", "AV", 2.0),
                ("aqi", "AV", 150.0),
            ],
            4: [
                ("banner", "Industrial smog at Peeragarhi; AV influx still climbing."),
                ("aqi", "PRG", 360.0),
                ("influx", "PRG", 2.4),
                ("factor", "ITO", "AV", 3.1),
                ("influx", "AV", 2.6),
                ("aqi", "AV", 205.0),
            ],
            5: [
                ("banner", "Anand Vihar breaches severe; live traffic incidents emerging."),
                ("aqi", "AV", 285.0),
                ("influx", "AV", 2.8),
            ],
            6: [("banner", "Congestion peak; AI re-optimising around blocked corridors.")],
            7: [("banner", "Second wave: ITO commercial belt breaches threshold."),
                ("aqi", "ITO", 420.0), ("influx", "ITO", 2.6)],
            9: [("banner", "Congestion easing; AI consolidates remaining hotspots.")],
        }

    # ================================================================== #
    # Per-tick environment dynamics                                       #
    # ================================================================== #
    def _update_environment(self, tick: int) -> None:
        """Advance background dynamics, then overlay scripted shocks."""
        # 1. Mean-reverting traffic influx + congestion noise.
        for node in self.graph.nodes():
            base = self._influx_base[node.node_id]
            node.traffic_rate_influx = max(
                0.3,
                node.traffic_rate_influx
                + (base - node.traffic_rate_influx) * 0.4
                + self.rng.uniform(-0.12, 0.12),
            )
        for edge in self.graph.edges():
            base = self._factor_base[edge.key]
            edge.set_factor(
                edge.traffic_density_factor
                + (base - edge.traffic_density_factor) * 0.4
                + self.rng.uniform(-0.15, 0.15)
            )

        # 2. Passive AQI accrual (non-infrastructure cells pollute fastest).
        for node in self.graph.nodes():
            if node.is_infrastructure:
                node.current_AQI_PM25 += 0.4 * node.traffic_rate_influx
            else:
                node.accrue_pollution()

        # 3. Scripted shocks override the relevant state for this tick.
        for event in self.scenario.get(tick, []):
            kind = event[0]
            if kind == "aqi":
                self.graph.node(event[1]).current_AQI_PM25 = event[2]
            elif kind == "influx":
                self.graph.node(event[1]).traffic_rate_influx = event[2]
            elif kind == "factor":
                self.graph.edge(event[1], event[2]).set_factor(event[3])
            # "banner" handled at render time.

        # 4. Freeze readings into the rolling history buffers for analytics
        #    BEFORE the incident director acts, so one-off blockages are not
        #    mistaken for traffic *trends* by the predictive engine.
        self.graph.snapshot_all_history()

        # 5. Live incident director: block the exact segment a mission truck is on.
        self._dynamic_events(tick)

    def _gridlock_edge(self, u: str, v: str) -> None:
        """Force both directions of ``u<->v`` into total-blockage gridlock.

        The factor is chosen so the realised speed is ~3.5 km/h (below the 5 km/h
        STUCK threshold) regardless of the segment's design speed.
        """
        for a, b in ((u, v), (v, u)):
            if self.graph.has_edge(a, b):
                edge = self.graph.edge(a, b)
                edge.set_factor(min(TRAFFIC_FACTOR_MAX, edge.base_speed / 3.5))

    def _dynamic_events(self, tick: int) -> None:
        """Inject targeted gridlock to exercise both STUCK exception branches.

        Scans active mission trucks and, at most once each:
          * blocks a truck already *inside* its hotspot zone  -> in-hotspot trap;
          * blocks a truck still *far from* its hotspot       -> en-route trap.
        """
        self._incident_banner = ""
        if tick < 4:
            return
        for truck in self.fleet:
            if truck.operational_status != OperationalStatus.EN_ROUTE:
                continue
            if truck.route_purpose != "MISSION" or not truck.mission_id:
                continue
            if tick < truck.hold_until_tick:
                continue  # still loitering for ETA sync
            if not truck.route or truck.route_index + 1 >= len(truck.route):
                continue
            hotspot = self.graph.node(truck.mission_id)
            u = truck.route[truck.route_index]
            v = truck.route[truck.route_index + 1]
            in_zone = hotspot.contains_point(truck.x, truck.y)

            if in_zone and not self._director["inhotspot_done"]:
                self._gridlock_edge(u, v)
                self._director["inhotspot_done"] = True
                self._incident_banner = (
                    f"INCIDENT: gridlock pile-up inside the {hotspot.name} zone "
                    f"boxes in {truck.truck_id} on final approach."
                )
            elif (not in_zone) and not self._director["interception_done"]:
                self._gridlock_edge(u, v)
                self._director["interception_done"] = True
                self._incident_banner = (
                    f"INCIDENT: stalled traffic blocks {u}->{v}; {truck.truck_id} "
                    f"trapped far from {hotspot.name}."
                )

    def _advance_fleet(self, tick: int) -> dict:
        """Integrate one tick of motion for every EN_ROUTE truck."""
        results: dict[str, MoveResult] = {}
        for truck in self.fleet:
            if truck.operational_status == OperationalStatus.EN_ROUTE:
                results[truck.truck_id] = truck.advance(self.graph, tick)
        return results

    # ================================================================== #
    # Main loop                                                           #
    # ================================================================== #
    def run_ticks(self, num_ticks: int) -> None:
        """Execute ``num_ticks`` chronological simulation steps with dashboards.

        ``verbose`` toggles the per-tick dashboard; the intro banner and final
        summary always print so a ``--quiet`` run still reports its headline.
        """
        self._render_intro()
        for tick in range(1, num_ticks + 1):
            self.coordinator.begin_tick(tick)
            self._update_environment(tick)
            self.coordinator.ingest_telemetry()
            self.coordinator.run_prediction()
            self.coordinator.run_dispatch()
            self.coordinator.assign_patrols()
            results = self._advance_fleet(tick)
            self.coordinator.process_movement(results)
            self.coordinator.run_spraying()
            self.coordinator.run_road_cleaning()
            self.coordinator.run_supply_lifecycle()
            self.coordinator.recover_stuck()
            self.coordinator.close_missions()
            self.coordinator.ingest_telemetry()
            self.frames.append(self._capture_frame(tick))
            if self.verbose:
                self._render_dashboard(tick)
        self._render_summary(num_ticks)

    # ================================================================== #
    # Dashboard rendering                                                 #
    # ================================================================== #
    def _render_intro(self) -> None:
        print(_LINE)
        print(" AGENTIC AI POLLUTION-CONTROL SYSTEM  |  Delhi Anti-Smog Tanker Network")
        print(" Central AI Coordinator + Modified Multi-Objective Dijkstra Dispatcher")
        print(_LINE)
        print(f" Topology : {len(self.graph)} nodes "
              f"({len(self.graph.nodes_of_type(NodeType.JUNCTION))} junctions, "
              f"{len(self.graph.nodes_of_type(NodeType.STP))} STP, "
              f"{len(self.graph.nodes_of_type(NodeType.REFUELING))} refuel) | "
              f"{sum(1 for _ in self.graph.edges())} directed edges")
        print(f" Fleet    : {len(self.fleet)} tankers "
              f"({', '.join(t.truck_id + ':' + t.capacity_class.name for t in self.fleet)})")
        print(f" Tick     : {TICK_MINUTES:.0f} simulated minutes")
        print(_LINE)

    def _render_dashboard(self, tick: int) -> None:
        """Emit the structured per-tick console dashboard."""
        coord = self.coordinator
        banners = [e[1] for e in self.scenario.get(tick, []) if e[0] == "banner"]

        print("")
        print(_LINE)
        header = (f" TICK {tick:02d}  |  T+{tick * TICK_MINUTES:.0f} min  |  "
                  f"Active missions: {len(coord.active_missions)}  |  "
                  f"Resolved: {coord.missions_resolved}  |  "
                  f"Fast-pass billed: INR {coord.total_billed_inr:.0f}")
        print(header)
        if banners:
            print(f"   SCENARIO: {banners[0]}")
        if self._incident_banner:
            print(f"   {self._incident_banner}")
        print(_LINE)

        # --- AI event log --------------------------------------------- #
        print("-- AI COORDINATOR EVENT LOG " + "-" * 68)
        if coord.events:
            for line in coord.events:
                print("  " + line)
        else:
            print("  (no coordinator actions this tick)")

        # --- Network / AQI state -------------------------------------- #
        print("-- NETWORK / AQI STATE " + "-" * 73)
        print(f"  {'Node':<16}{'Type':<10}{'PM2.5':>7} {'Band':<13}{'Influx':>7}  Flag")
        for node in self.graph.nodes():
            flag = ""
            if not node.is_infrastructure and node.is_critical:
                flag = "*** HOTSPOT ***"
            elif node.node_id in coord.active_missions and coord.active_missions[node.node_id].is_predictive:
                flag = ">> pre-alert"
            band = f"{node.aqi_category.name} {node.aqi_category.glyph}"
            print(f"  {node.name:<16}{node.node_type.value:<10}"
                  f"{node.current_AQI_PM25:>7.0f} {band:<13}"
                  f"{node.traffic_rate_influx:>7.2f}  {flag}")

        # --- Fleet telemetry ------------------------------------------ #
        print("-- FLEET TELEMETRY " + "-" * 77)
        print(f"  {'Truck':<6}{'Class':<7}{'Status':<13}{'Loc':<7}{'Tgt':<7}"
              f"{'Water':<14}{'Fuel':>5}  {'Spd':>5}  Note")
        for truck in self.fleet:
            water = f"{truck.water_level_liters:.0f}L({truck.water_fraction * 100:.0f}%)"
            tgt = truck.target_node or "-"
            note = self._truck_note(truck, tick)
            print(f"  {truck.truck_id:<6}{truck.capacity_class.name:<7}"
                  f"{truck.operational_status.value:<13}{truck.current_node:<7}{tgt:<7}"
                  f"{water:<14}{truck.fuel_energy_pct:>4.0f}%  {truck.current_speed_kmh:>4.1f}  {note}")

        # --- Notable congestion --------------------------------------- #
        notable = sorted(
            (e for e in self.graph.edges() if e.traffic_density_factor >= 2.5),
            key=lambda e: e.traffic_density_factor,
            reverse=True,
        )[:6]
        if notable:
            print("-- CONGESTION HOTSPOTS (edges) " + "-" * 65)
            for e in notable:
                tag = "[GRIDLOCK]" if e.effective_speed_kmh() < 5.0 else "[congested]"
                pen = f" emit+{e.emission_penalty:.2f}" if e.emission_penalty > 0 else ""
                print(f"  {e.source:>5} -> {e.target:<6} factor {e.traffic_density_factor:>4.1f}  "
                      f"eff {e.effective_speed_kmh():>5.1f} km/h  {tag}{pen}")
        print(_LINE)

    def _truck_note(self, truck: TankerTruck, tick: int) -> str:
        """Concise human-readable annotation for the fleet table."""
        st = truck.operational_status
        if truck.stationary_misting:
            return "stationary curtain (trapped)"
        if st == OperationalStatus.EN_ROUTE:
            nxt = ""
            if truck.route and truck.route_index + 1 < len(truck.route):
                nxt = truck.route[truck.route_index + 1]
            if tick < truck.hold_until_tick:
                return f"ETA-sync loiter -> next {nxt}"
            purpose = {"MISSION": "to hotspot", "REPLENISH_WATER": "to STP",
                       "REPLENISH_FUEL": "to CNG", "PATROL": "washing roads"}.get(truck.route_purpose, "")
            lock = " [console LOCKED]" if truck.console_locked else ""
            return f"-> {nxt} ({purpose}){lock}"
        if st == OperationalStatus.SPRAYING:
            return "open spraying"
        if st == OperationalStatus.REPLENISHING:
            return "replenishing [console LOCKED]"
        if st == OperationalStatus.STUCK:
            return "STUCK - awaiting clearance"
        return "available"

    def _render_summary(self, num_ticks: int) -> None:
        print("")
        print(_LINE)
        print(" SIMULATION COMPLETE")
        print(_LINE)
        junctions = [n for n in self.graph.nodes() if not n.is_infrastructure]
        avg_aqi = sum(n.current_AQI_PM25 for n in junctions) / max(1, len(junctions))
        print(f"  Ticks executed        : {num_ticks} ({num_ticks * TICK_MINUTES:.0f} simulated minutes)")
        print(f"  Missions resolved     : {self.coordinator.missions_resolved}")
        print(f"  Missions still open   : {len(self.coordinator.active_missions)}")
        print(f"  Mean junction PM2.5   : {avg_aqi:.0f} ug/m3")
        print(f"  Fast-pass micro-txns  : INR {self.coordinator.total_billed_inr:.0f}")
        print("  Final fleet state:")
        for t in self.fleet:
            print(f"    {t.truck_id} [{t.capacity_class.name:<6}] {t.operational_status.value:<12} "
                  f"@ {t.current_node:<6} water {t.water_fraction * 100:>3.0f}%  fuel {t.fuel_energy_pct:>3.0f}%")
        print(_LINE)

    # ================================================================== #
    # Visualiser data export                                              #
    # ================================================================== #
    def viz_meta(self) -> dict:
        """Static scene description (node positions + road links) for the UI."""
        nodes = [
            {
                "id": n.node_id,
                "name": n.name,
                "x": n.x,
                "y": n.y,
                "type": n.node_type.value,
                "radius_km": n.radius_km,
                "lat": n.lat,
                "lng": n.lng,
                "line": n.line,
            }
            for n in self.graph.nodes()
        ]
        seen: set[tuple] = set()
        links = []
        for e in self.graph.edges():
            key = tuple(sorted((e.source, e.target)))
            if key in seen:
                continue
            seen.add(key)
            # Use the edge oriented key[0]->key[1] so the road geometry matches.
            oriented = self.graph.edge(key[0], key[1])
            links.append({"s": key[0], "t": key[1], "line": oriented.line,
                          "color": oriented.line_color, "geom": oriented.geometry})
        # Directed, weighted edge list so the Routing Engine view can run Dijkstra
        # in the browser (weight = free-flow travel time in hours).
        edges_directed = [
            {"s": e.source, "t": e.target, "d": round(e.distance_km, 2),
             "w": round(e.distance_km / e.base_speed, 4)}
            for e in self.graph.edges()
        ]
        xs = [n["x"] for n in nodes]
        ys = [n["y"] for n in nodes]
        return {
            "nodes": nodes,
            "links": links,
            "edges": edges_directed,
            "bounds": {"minx": min(xs), "maxx": max(xs), "miny": min(ys), "maxy": max(ys)},
            "tick_minutes": TICK_MINUTES,
            "fleet": [{"id": t.truck_id, "class": t.capacity_class.name, "role": t.role}
                      for t in self.fleet],
        }

    def _capture_frame(self, tick: int) -> dict:
        """Serialise the current dynamic world state for one animation frame."""
        coord = self.coordinator
        nodes = []
        for n in self.graph.nodes():
            mission = coord.active_missions.get(n.node_id)
            nodes.append({
                "id": n.node_id,
                "aqi": round(n.current_AQI_PM25, 0),
                "band": n.aqi_category.name,
                "influx": round(n.traffic_rate_influx, 2),
                "hotspot": (not n.is_infrastructure) and n.is_critical,
                "predictive": bool(mission and mission.is_predictive),
            })
        trucks = []
        for t in self.fleet:
            seg_from, seg_to, frac = t.current_node, None, 0.0
            if (
                t.operational_status == OperationalStatus.EN_ROUTE
                and t.route
                and t.route_index + 1 < len(t.route)
            ):
                seg_from = t.route[t.route_index]
                seg_to = t.route[t.route_index + 1]
                dist = self.graph.edge(seg_from, seg_to).distance_km
                frac = 0.0 if dist <= 0 else min(1.0, t.edge_progress_km / dist)
            trucks.append({
                "id": t.truck_id,
                "class": t.capacity_class.name,
                "status": t.operational_status.value,
                "x": round(t.x, 2),
                "y": round(t.y, 2),
                "node": t.current_node,
                "from": seg_from,
                "to": seg_to,
                "frac": round(frac, 3),
                "water": round(t.water_fraction * 100, 0),
                "fuel": round(t.fuel_energy_pct, 0),
                "target": t.target_node or "",
                "note": self._truck_note(t, tick + 1),
                "stationary": t.stationary_misting,
                "role": t.role,
                "route": list(t.route),          # Dijkstra-computed path (node ids)
                "route_idx": t.route_index,        # current position along the path
                "purpose": t.route_purpose,
                "locked": t.console_locked,        # AI has overridden the in-cab console
            })
        congested = [
            {"s": e.source, "t": e.target, "factor": round(e.traffic_density_factor, 1)}
            for e in self.graph.edges()
            if e.traffic_density_factor >= 2.5
        ]
        return {
            "tick": tick,
            "minute": round(tick * TICK_MINUTES),
            "missions_active": len(coord.active_missions),
            "missions_resolved": coord.missions_resolved,
            "billed": round(coord.total_billed_inr),
            "events": list(coord.events),
            "nodes": nodes,
            "trucks": trucks,
            "congested": congested,
        }

    def export_json(self, path: str) -> None:
        """Write ``{meta, frames}`` to ``path`` as JSON for external viewers."""
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"meta": self.viz_meta(), "frames": self.frames}, fh)
