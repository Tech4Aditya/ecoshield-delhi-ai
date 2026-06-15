"""
Agent 1: the Central AI Coordinator.

The coordinator owns global situational awareness (graph + fleet telemetry) and
runs, every tick, the decision pipeline:

    prediction -> dispatch -> movement reconciliation -> spraying
               -> supply lifecycle -> stuck recovery -> mission closure

It is the only component allowed to *command* trucks; trucks themselves are dumb
actuators.  All of the brief's exception workflows live here:

* Predictive spike pre-emption (``run_prediction``).
* Multi-truck workload splitting + ETA synchronisation (``run_dispatch``).
* "Stuck in traffic" -> in-hotspot stationary misting vs en-route interception &
  reallocation (``process_movement``).
* Autonomous closed-loop water/fuel replenishment (``run_supply_lifecycle``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import (
    CLEANER_FUEL_PER_TICK,
    CLEANER_WATER_PER_TICK,
    CLEARED_PM25,
    CRITICAL_PM25,
    DUST_SUPPRESS_PER_TICK,
    FASTPASS_FUEL_RATE_PER_PCT,
    FASTPASS_WATER_RATE_PER_KL,
    MAX_SUBFLEET,
    PREDICT_LOOKBACK_TICKS,
    PREDICT_TRAFFIC_RATIO,
    SPRAY_AQI_PER_LITRE,
    SPRAY_BURN_PCT_PER_TICK,
    STATIONARY_MIST_EFFICIENCY,
    STUCK_SPEED_KMH,
    VREQ_MIN,
    VREQ_PER_AQI,
    VREQ_PREDICTIVE,
)
from .dispatch import FleetDispatcher
from .enums import NodeType, OperationalStatus
from .routing import MultiObjectiveRouter
from .topology import ServiceNode, TransitGraph
from .trucks import MoveResult, TankerTruck, Telemetry

# Pre-alert band: pre-emptive curtains are only worth dispatching once a
# predicted cell is already drifting toward the threshold (>= 60 % of critical).
PRE_ALERT_PM25 = 0.6 * CRITICAL_PM25
PREDICTIVE_MIN_TICKS = 4  # keep a pre-emptive curtain up at least this long


@dataclass
class Mission:
    """A mitigation campaign against one hotspot cell."""

    hotspot_id: str
    v_req: float
    opened_tick: int
    is_predictive: bool = False
    delivered_liters: float = 0.0
    announced: bool = False

    @property
    def min_close_tick(self) -> int:
        """Earliest tick a *predictive* mission may be retired."""
        return self.opened_tick + (PREDICTIVE_MIN_TICKS if self.is_predictive else 0)


class CentralAICoordinator:
    """Decentralised-network brain: telemetry, prediction, dispatch, exceptions."""

    def __init__(
        self,
        graph: TransitGraph,
        fleet: list[TankerTruck],
        router: MultiObjectiveRouter,
        dispatcher: FleetDispatcher,
    ) -> None:
        self.graph = graph
        self.fleet = fleet
        self.router = router
        self.dispatcher = dispatcher

        self._by_id: dict[str, TankerTruck] = {t.truck_id: t for t in fleet}
        self.telemetry: dict[str, Telemetry] = {}
        self.active_missions: dict[str, Mission] = {}
        self.predicted: set[str] = set()
        self.events: list[str] = []
        self.tick: int = 0

        # Closed-loop billing ledger (mocked fast-pass micro-transactions).
        self._replenish_ledger: dict[str, dict[str, float]] = {}
        self.total_billed_inr: float = 0.0
        self.missions_resolved: int = 0

    # ================================================================== #
    # Logging helper                                                      #
    # ================================================================== #
    def _log(self, message: str) -> None:
        self.events.append(message)

    def begin_tick(self, tick: int) -> None:
        """Reset per-tick scratch state at the start of a simulation step."""
        self.tick = tick
        self.events = []
        self.predicted = set()

    # ================================================================== #
    # Telemetry ingestion                                                 #
    # ================================================================== #
    def ingest_telemetry(self) -> None:
        """Pull a fresh snapshot from every truck into the global store."""
        for truck in self.fleet:
            truck.sync_position(self.graph)
            self.telemetry[truck.truck_id] = truck.telemetry()

    # ================================================================== #
    # Predictive analytics engine                                         #
    # ================================================================== #
    def run_prediction(self) -> set[str]:
        """Flag imminent AQI breaches from accelerating traffic influx.

        For every edge, compare the live congestion factor against its value
        ``PREDICT_LOOKBACK_TICKS`` ticks ago.  A rise exceeding
        ``PREDICT_TRAFFIC_RATIO`` (>40 %) is treated as a leading indicator that
        the *destination* cell will breach before its physical sensor reflects
        it -- so we pre-emptively flag that node.
        """
        predicted: set[str] = set()
        for edge in self.graph.edges():
            # Compare the two most recent *recorded* samples (trend), not the
            # live value -- this excludes one-off incident spikes injected after
            # the history snapshot, keeping prediction a genuine trend signal.
            current = edge.factor_n_ticks_ago(0)
            past = edge.factor_n_ticks_ago(PREDICT_LOOKBACK_TICKS)
            if current is None or past is None or past <= 0:
                continue
            ratio = current / past
            if ratio <= PREDICT_TRAFFIC_RATIO:
                continue
            dest = self.graph.node(edge.target)
            if dest.is_infrastructure:
                continue
            if dest.node_id in predicted:
                continue
            # Skip cells already breached (those are active, not predictive) and
            # cells not yet trending toward the threshold.
            if dest.is_critical or dest.current_AQI_PM25 < PRE_ALERT_PM25:
                continue
            predicted.add(dest.node_id)
            pct = (ratio - 1.0) * 100.0
            self._log(
                f"[PREDICT] {edge.source}->{edge.target} influx +{pct:.0f}% over "
                f"{PREDICT_LOOKBACK_TICKS} ticks -> pre-emptive curtain queued for "
                f"{dest.name} (AQI {dest.current_AQI_PM25:.0f}) ahead of sensor breach."
            )
        self.predicted = predicted
        return predicted

    # ================================================================== #
    # Dispatch: mission management + workload splitting                   #
    # ================================================================== #
    def _committed_trucks(self, hotspot_id: str) -> list[TankerTruck]:
        """Trucks actively servicing (en-route or spraying) a given hotspot."""
        return [
            t
            for t in self.fleet
            if t.mission_id == hotspot_id
            and t.operational_status in (OperationalStatus.EN_ROUTE, OperationalStatus.SPRAYING)
        ]

    @staticmethod
    def _vreq_for_aqi(aqi: float) -> float:
        """Water volume (L) required to mitigate a cell at ``aqi`` ug/m3."""
        return max(VREQ_MIN, (aqi - CRITICAL_PM25) * VREQ_PER_AQI)

    def run_dispatch(self) -> None:
        """Open/update missions for hotspots and assign synchronised sub-fleets."""
        # 1. Active (sensor-confirmed) hotspots.
        for node in self.graph.nodes():
            if node.is_infrastructure or not node.is_critical:
                continue
            vreq = self._vreq_for_aqi(node.current_AQI_PM25)
            mission = self.active_missions.get(node.node_id)
            if mission is None:
                self.active_missions[node.node_id] = Mission(
                    hotspot_id=node.node_id, v_req=vreq, opened_tick=self.tick
                )
            else:
                mission.v_req = max(mission.v_req, vreq)
                mission.is_predictive = False  # escalate predictive -> confirmed

        # 2. Predicted (pre-breach) hotspots.
        for nid in self.predicted:
            node = self.graph.node(nid)
            if node.is_critical or nid in self.active_missions:
                continue
            self.active_missions[nid] = Mission(
                hotspot_id=nid,
                v_req=VREQ_PREDICTIVE,
                opened_tick=self.tick,
                is_predictive=True,
            )

        # 3. Dispatch / top-up every open mission (worst first).
        for mission in sorted(
            self.active_missions.values(),
            key=lambda m: self.graph.node(m.hotspot_id).current_AQI_PM25,
            reverse=True,
        ):
            self._dispatch_to_mission(mission)

    def _dispatch_to_mission(self, mission: Mission) -> None:
        """Compute the shortfall for a mission and assign a staggered sub-fleet."""
        node = self.graph.node(mission.hotspot_id)
        committed = self._committed_trucks(mission.hotspot_id)
        covered = mission.delivered_liters + sum(t.water_level_liters for t in committed)
        remaining = mission.v_req - covered
        free_slots = MAX_SUBFLEET - len(committed)
        if remaining <= 0 or free_slots <= 0:
            return

        matrix = self.dispatcher.efficiency_matrix(self.fleet, mission.hotspot_id, remaining)
        if not matrix:
            if not mission.announced:
                kind = "predictive" if mission.is_predictive else "ACTIVE"
                self._log(
                    f"[DISPATCH] {kind} hotspot {node.name} (AQI {node.current_AQI_PM25:.0f}, "
                    f"V_req {mission.v_req:.0f}L): no tanker within viable radius -- monitoring."
                )
                mission.announced = True
            return

        selected = self.dispatcher.select_subfleet(matrix, remaining, max_trucks=free_slots)
        slots = self.dispatcher.synchronize_etas(selected, self.tick)
        if not slots:
            return

        ids = ", ".join(s.candidate.truck_id for s in slots)
        kind = "PREDICTIVE" if mission.is_predictive else "ACTIVE"
        tag = "DISPATCH" if not committed else "TOP-UP"
        self._log(
            f"[{tag}] {kind} hotspot {node.name} | AQI {node.current_AQI_PM25:.0f} | "
            f"V_req {mission.v_req:.0f}L | shortfall {remaining:.0f}L -> sub-fleet [{ids}]"
        )
        self._log(
            "          Efficiency-Score Matrix (top): "
            + "; ".join(
                f"{c.truck_id}={c.score:.2f}(ETA {c.eta_min:.0f}m,{c.deliverable_liters:.0f}L)"
                for c in matrix[: max(3, len(slots))]
            )
        )

        for slot in slots:
            truck = self._by_id[slot.candidate.truck_id]
            truck.assign_route(
                slot.candidate.route.path,
                mission.hotspot_id,
                purpose="MISSION",
                mission_id=mission.hotspot_id,
                planned_delivery=slot.candidate.deliverable_liters,
                hold_until_tick=slot.hold_until_tick,
            )
            wait = slot.hold_until_tick - self.tick
            wait_txt = "depart now" if wait <= 0 else f"loiter {wait} tick(s) then depart"
            self._log(
                f"          -> {truck.truck_id} [{truck.capacity_class.name}] via "
                f"{slot.candidate.route.describe()} | {wait_txt} | "
                f"ETA t{slot.arrival_tick}, spray-out t{slot.finish_tick}"
            )
        mission.announced = True

    # ================================================================== #
    # Movement reconciliation: arrivals + STUCK exceptions                #
    # ================================================================== #
    def process_movement(self, results: dict[str, MoveResult]) -> None:
        """Reconcile the tick's motion: handle arrivals and < 5 km/h anomalies."""
        for truck in self.fleet:
            result = results.get(truck.truck_id)
            if result is None:
                continue
            if result.loitering:
                continue
            if result.arrived:
                self._handle_arrival(truck)
                continue
            # Anomaly detection: an EN_ROUTE truck crawling below 5 km/h.
            if (
                truck.operational_status == OperationalStatus.EN_ROUTE
                and result.speed_kmh < STUCK_SPEED_KMH
            ):
                self._handle_stuck(truck, result)

    def _handle_arrival(self, truck: TankerTruck) -> None:
        """Transition a truck that reached its target this tick."""
        truck.current_speed_kmh = 0.0
        if truck.route_purpose == "MISSION":
            mission = self.active_missions.get(truck.mission_id or "")
            node = self.graph.node(truck.current_node)
            if mission is None or node.current_AQI_PM25 < CLEARED_PM25:
                self._log(
                    f"[STAND-DOWN] {truck.truck_id} reached {node.name} but cell already "
                    f"mitigated -- returning to available pool."
                )
                truck.reset_to_idle(truck.current_node)
            else:
                truck.operational_status = OperationalStatus.SPRAYING
                truck.stationary_misting = False
                self._log(
                    f"[ON-SITE] {truck.truck_id} arrived at {node.name}; misting cannons "
                    f"engaged ({truck.water_level_liters:.0f}L onboard)."
                )
        elif truck.route_purpose in ("REPLENISH_WATER", "REPLENISH_FUEL"):
            self._begin_replenishment(truck)
        elif truck.route_purpose == "PATROL":
            # Road cleaner finished a patrol leg; free it for a fresh route.
            truck.reset_to_idle(truck.current_node)

    def _handle_stuck(self, truck: TankerTruck, result: MoveResult) -> None:
        """Branch the brief's two STUCK sub-routines.

        * In-hotspot trapped -> stationary misting curtain (keep the mission).
        * En-route interception -> revoke target, mark STUCK, reallocate workload.
        """
        node = self.graph.node(truck.current_node)

        # Replenishment runs are not hotspot missions; just note the crawl.
        if truck.route_purpose != "MISSION" or truck.mission_id is None:
            self._log(
                f"[CRAWL] {truck.truck_id} at {node.name} ({result.speed_kmh:.1f} km/h) "
                f"en route to {truck.route_purpose.split('_')[-1].lower()} -- holding course."
            )
            return

        hotspot = self.graph.node(truck.mission_id)
        in_zone = hotspot.contains_point(truck.x, truck.y) or truck.current_node == hotspot.node_id

        if in_zone:
            # --- Exception Rule 1: In-Hotspot Trapped --------------------- #
            # The truck is physically inside the pollution zone but boxed in by
            # gridlock. Treat reaching the zone as on-site arrival so its curtain
            # mitigates the correct cell, then mist in place against idling exhaust.
            truck.current_node = hotspot.node_id
            truck.x, truck.y = hotspot.x, hotspot.y
            truck.route = [hotspot.node_id]
            truck.route_index = 0
            truck.edge_progress_km = 0.0
            truck.target_node = hotspot.node_id
            truck.stationary_misting = True
            truck.stuck_edge = result.current_edge
            truck.operational_status = OperationalStatus.SPRAYING
            truck.current_speed_kmh = result.speed_kmh
            self._log(
                f"[EXCEPTION IN-HOTSPOT] {truck.truck_id} trapped inside {hotspot.name} "
                f"zone at {result.speed_kmh:.1f} km/h. Engaging STATIONARY misting curtain "
                f"(pitch-adjusted) to knock down idling exhaust of gridlocked vehicles."
            )
        else:
            # --- Exception Rule 2: En-Route Interception ------------------ #
            mission = self.active_missions.get(truck.mission_id)
            shortfall = truck.water_level_liters
            truck.operational_status = OperationalStatus.STUCK
            truck.console_locked = True
            truck.stuck_edge = result.current_edge
            truck.stuck_since_tick = self.tick
            truck.current_speed_kmh = result.speed_kmh
            stuck_mission_id = truck.mission_id
            truck.mission_id = None
            truck.route = []
            truck.target_node = None
            truck.route_purpose = "IDLE"

            base_msg = (
                f"[EXCEPTION EN-ROUTE] {truck.truck_id} stuck at {node.name} "
                f"({result.speed_kmh:.1f} km/h). Route revoked; driver console LOCKED."
            )
            if mission is not None:
                replacement = self._emergency_replace(mission, shortfall, exclude_id=truck.truck_id)
                if replacement is not None:
                    repl, route = replacement
                    self._log(
                        base_msg
                        + f" Re-allocating {shortfall:.0f}L to {repl.truck_id} via unblocked "
                        f"bypass [{route.describe()}]..."
                    )
                else:
                    self._log(base_msg + " No unblocked unit available -- workload re-queued.")
            else:
                self._log(base_msg + f" (mission {stuck_mission_id} already closed).")

    def _emergency_replace(
        self, mission: Mission, shortfall: float, *, exclude_id: str
    ) -> Optional[tuple]:
        """Assign the best unblocked available truck to cover a revoked share.

        Returns ``(truck, route)`` for the chosen replacement, or ``None`` if no
        viable unit exists.  The replacement departs immediately (no loiter gate)
        since it is plugging a live gap, and its route is freshly recomputed on
        the post-incident graph so it inherently avoids the gridlocked segment.
        """
        matrix = self.dispatcher.efficiency_matrix(
            self.fleet, mission.hotspot_id, max(shortfall, VREQ_MIN)
        )
        for cand in matrix:
            if cand.truck_id == exclude_id:
                continue
            truck = self._by_id[cand.truck_id]
            truck.assign_route(
                cand.route.path,
                mission.hotspot_id,
                purpose="MISSION",
                mission_id=mission.hotspot_id,
                planned_delivery=cand.deliverable_liters,
                hold_until_tick=self.tick,
            )
            return truck, cand.route
        return None

    # ================================================================== #
    # Spraying: convert water -> AQI reduction                            #
    # ================================================================== #
    def run_spraying(self) -> None:
        """Apply one tick of atomisation for every spraying/misting tanker."""
        for truck in self.fleet:
            if truck.operational_status != OperationalStatus.SPRAYING:
                continue
            mission = self.active_missions.get(truck.mission_id or "")
            node = self.graph.node(truck.current_node)

            # If the specific segment that trapped a stationary-misting truck has
            # cleared, drop the reduced-efficiency curtain and resume open spray.
            if truck.stationary_misting:
                trap = truck.stuck_edge
                trap_cleared = (
                    trap is None
                    or not self.graph.has_edge(*trap)
                    or self.graph.edge(*trap).effective_speed_kmh() >= STUCK_SPEED_KMH
                )
                if trap_cleared:
                    truck.stationary_misting = False
                    truck.stuck_edge = None

            efficiency = STATIONARY_MIST_EFFICIENCY if truck.stationary_misting else 1.0
            dispensed = truck.spray(efficiency)
            truck.burn_idle_fuel(SPRAY_BURN_PCT_PER_TICK)
            drop = node.knock_down_aqi(dispensed * SPRAY_AQI_PER_LITRE)
            if mission is not None:
                mission.delivered_liters += dispensed

            mode = "stationary curtain" if truck.stationary_misting else "open spray"
            self._log(
                f"[SPRAY] {truck.truck_id} {mode} at {node.name}: {dispensed:.0f}L -> "
                f"AQI -{drop:.0f} (now {node.current_AQI_PM25:.0f}), {truck.water_level_liters:.0f}L left."
            )

            if truck.water_level_liters <= 1.0:
                truck.stationary_misting = False
                if self._node_is_passable(truck.current_node):
                    truck.reset_to_idle(truck.current_node)
                    self._log(
                        f"[EMPTY] {truck.truck_id} discharged its load at {node.name}; "
                        f"released for replenishment routing."
                    )
                else:
                    truck.operational_status = OperationalStatus.STUCK
                    truck.mission_id = None
                    self._log(
                        f"[EMPTY] {truck.truck_id} empty but still gridlocked at {node.name}; "
                        f"awaiting clearance."
                    )

    def _node_is_passable(self, node_id: str) -> bool:
        """True if at least one outgoing edge currently exceeds the stuck speed."""
        for nbr in self.graph.neighbors(node_id):
            if self.graph.edge(node_id, nbr).effective_speed_kmh() >= STUCK_SPEED_KMH:
                return True
        return not self.graph.neighbors(node_id)

    # ================================================================== #
    # Road-cleaning fleet: continuous patrol + dust suppression           #
    # ================================================================== #
    def _road_cleaners(self) -> list[TankerTruck]:
        return [t for t in self.fleet if t.role == "CLEANER"]

    def _next_patrol_target(self, truck: TankerTruck) -> Optional[str]:
        """Pick the next leg for a road cleaner -- bias toward the dustiest, busiest
        corridors, rotated per-truck so the fleet spreads across the network."""
        busy = sorted(
            (n for n in self.graph.nodes() if not n.is_infrastructure),
            key=lambda n: n.traffic_rate_influx,
            reverse=True,
        )
        if not busy:
            return None
        try:
            offset = int(truck.truck_id.split("-")[-1])
        except ValueError:
            offset = 0
        idx = (self.tick + offset) % min(8, len(busy))
        target = busy[idx].node_id
        if target == truck.current_node:
            target = busy[(idx + 1) % len(busy)].node_id
        return target

    def assign_patrols(self) -> None:
        """Send idle, adequately-supplied road cleaners out on a fresh patrol leg.

        Runs before fleet movement so the cleaners have a route to follow this tick.
        """
        for truck in self._road_cleaners():
            if truck.operational_status != OperationalStatus.IDLE:
                continue
            if truck.is_low_water or truck.is_low_fuel:
                continue  # the supply lifecycle will route it to a depot
            target = self._next_patrol_target(truck)
            if target is None:
                continue
            route = self.router.shortest_path(truck.current_node, target, truck.capacity_class)
            if route is not None and not route.is_trivial:
                truck.assign_route(route.path, target, purpose="PATROL")

    def run_road_cleaning(self) -> None:
        """Apply dust suppression for every patrolling cleaner that moved this tick.

        Washing the road binds settled dust, so the cell the truck is on (and the
        one it is heading into) shed PM that would otherwise be resuspended.
        """
        for truck in self._road_cleaners():
            if (
                truck.operational_status != OperationalStatus.EN_ROUTE
                or truck.route_purpose != "PATROL"
                or truck.water_level_liters <= 0
                or self.tick < truck.hold_until_tick
            ):
                continue
            here = self.graph.node(truck.current_node)
            drop = here.knock_down_aqi(DUST_SUPPRESS_PER_TICK)
            ahead = None
            if truck.route and truck.route_index + 1 < len(truck.route):
                ahead = self.graph.node(truck.route[truck.route_index + 1])
                drop += ahead.knock_down_aqi(DUST_SUPPRESS_PER_TICK * 0.5)
            truck.water_level_liters = max(0.0, truck.water_level_liters - CLEANER_WATER_PER_TICK)
            truck.burn_idle_fuel(CLEANER_FUEL_PER_TICK)

    # ================================================================== #
    # Closed-loop supply lifecycle                                        #
    # ================================================================== #
    def run_supply_lifecycle(self) -> None:
        """Enforce water/fuel floors and progress active replenishments."""
        for truck in self.fleet:
            if truck.operational_status == OperationalStatus.REPLENISHING:
                self._progress_replenishment(truck)
                continue
            # The AI interrupts any idle/spraying/en-route-to-mission truck that
            # breaches a consumable floor (replenishment pre-empts mitigation).
            if truck.operational_status in (
                OperationalStatus.IDLE,
                OperationalStatus.SPRAYING,
            ) or (
                truck.operational_status == OperationalStatus.EN_ROUTE
                and truck.route_purpose in ("MISSION", "PATROL")
            ):
                if truck.is_low_fuel:
                    self._route_to_facility(truck, NodeType.REFUELING, "REPLENISH_FUEL", "fuel")
                elif truck.is_low_water:
                    self._route_to_facility(truck, NodeType.STP, "REPLENISH_WATER", "water")

    def _route_to_facility(
        self, truck: TankerTruck, node_type: NodeType, purpose: str, resource: str
    ) -> None:
        """Interrupt a truck and lock its console onto the nearest facility."""
        route = self.router.nearest_facility(truck.current_node, node_type, truck.capacity_class)
        if route is None:
            self._log(f"[SUPPLY] {truck.truck_id} {resource} critical but no facility reachable!")
            return

        # Releasing a mission share here naturally lets run_dispatch top it up.
        was_mission = truck.mission_id
        if route.is_trivial:
            truck.target_node = truck.current_node
            truck.route = [truck.current_node]
            truck.route_purpose = purpose
            truck.mission_id = None
            truck.console_locked = True
            self._begin_replenishment(truck)
            return

        facility = self.graph.node(route.path[-1])
        val = f"{truck.fuel_energy_pct:.0f}%" if resource == "fuel" else f"{truck.water_fraction * 100:.0f}%"
        truck.assign_route(
            route.path,
            facility.node_id,
            purpose=purpose,
            mission_id=None,
            console_locked=True,
        )
        rel = f" (released from {was_mission})" if was_mission else ""
        self._log(
            f"[SUPPLY] {truck.truck_id} {resource} low at {val}{rel}. Driver console LOCKED. "
            f"AI routing to {facility.name} via {route.describe()}."
        )

    def _begin_replenishment(self, truck: TankerTruck) -> None:
        """Dock a truck at a facility and pre-authorise the fast-pass gate."""
        truck.operational_status = OperationalStatus.REPLENISHING
        truck.current_speed_kmh = 0.0
        self._replenish_ledger[truck.truck_id] = {"water_l": 0.0, "fuel_pct": 0.0}
        facility = self.graph.node(truck.current_node)
        self._log(
            f"[FASTPASS] Gate pre-authorised for {truck.truck_id} at {facility.name}; "
            f"micro-transaction token issued, barrier raised."
        )

    def _progress_replenishment(self, truck: TankerTruck) -> None:
        """Pump water / energy for one tick and reintegrate when topped up."""
        node = self.graph.node(truck.current_node)
        ledger = self._replenish_ledger.setdefault(truck.truck_id, {"water_l": 0.0, "fuel_pct": 0.0})

        # Polymorphic service: the facility itself knows how to replenish a truck.
        if not isinstance(node, ServiceNode) or node.replenish_purpose != truck.route_purpose:
            # Mismatched / non-service node (shouldn't happen) -- retry routing.
            truck.reset_to_idle(truck.current_node)
            return

        amount, ledger_key = node.service(truck)
        ledger[ledger_key] += amount
        done = node.is_satisfied(truck)

        if done:
            cost = (
                ledger["water_l"] / 1000.0 * FASTPASS_WATER_RATE_PER_KL
                + ledger["fuel_pct"] * FASTPASS_FUEL_RATE_PER_PCT
            )
            self.total_billed_inr += cost
            resource = "water" if truck.route_purpose == "REPLENISH_WATER" else "energy"
            level = (
                f"{truck.water_fraction * 100:.0f}% water"
                if resource == "water"
                else f"{truck.fuel_energy_pct:.0f}% charge"
            )
            self._log(
                f"[REPLENISH] {truck.truck_id} restored to {level} at {node.name} "
                f"(fast-pass INR {cost:.0f}). Reintegrated into available fleet queue."
            )
            self._replenish_ledger.pop(truck.truck_id, None)
            truck.reset_to_idle(truck.current_node)

    # ================================================================== #
    # Stuck recovery + mission closure                                    #
    # ================================================================== #
    def recover_stuck(self) -> None:
        """Return STUCK trucks to the pool once their gridlock clears."""
        for truck in self.fleet:
            if truck.operational_status != OperationalStatus.STUCK:
                continue
            # Keep the truck immobilised for at least the tick it got stuck.
            if self.tick <= truck.stuck_since_tick:
                continue
            if self._node_is_passable(truck.current_node):
                node = self.graph.node(truck.current_node)
                truck.reset_to_idle(truck.current_node)
                self._log(
                    f"[RECOVERED] {truck.truck_id} mobile again at {node.name}; "
                    f"returned to available fleet pool."
                )

    def close_missions(self) -> None:
        """Retire missions whose cells are mitigated and release their trucks."""
        for hotspot_id in list(self.active_missions.keys()):
            mission = self.active_missions[hotspot_id]
            node = self.graph.node(hotspot_id)
            cleared = node.current_AQI_PM25 < CLEARED_PM25
            predictive_expired = mission.is_predictive and self.tick >= mission.min_close_tick

            should_close = False
            if not mission.is_predictive and cleared:
                should_close = True
            elif mission.is_predictive and cleared and predictive_expired:
                should_close = True

            if not should_close:
                continue

            released = 0
            for truck in self.fleet:
                if truck.mission_id == hotspot_id and truck.operational_status in (
                    OperationalStatus.EN_ROUTE,
                    OperationalStatus.SPRAYING,
                ):
                    truck.reset_to_idle(truck.current_node)
                    released += 1
            kind = "Pre-emptive curtain" if mission.is_predictive else "Hotspot"
            self._log(
                f"[MISSION CLR] {kind} {node.name} mitigated: AQI back to "
                f"{node.current_AQI_PM25:.0f} (<{CLEARED_PM25:.0f}); "
                f"{mission.delivered_liters:.0f}L delivered, {released} tanker(s) released."
            )
            del self.active_missions[hotspot_id]
            self.missions_resolved += 1

    # ================================================================== #
    # Read-only views for the dashboard                                   #
    # ================================================================== #
    def active_hotspot_nodes(self) -> list:
        """Non-infrastructure nodes currently above the critical threshold."""
        return [n for n in self.graph.nodes() if not n.is_infrastructure and n.is_critical]
