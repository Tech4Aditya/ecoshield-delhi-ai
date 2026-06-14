"""
Agent 2: the mobile water-tanker trucks.

Each :class:`TankerTruck` is a self-contained kinematic actuator.  The human
driver physically steers, but the Central AI dictates the *route* and *target*;
the truck therefore exposes a clean command surface (``assign_route``,
``advance``, ``spray``, ``consume_fuel``) and pushes a :class:`Telemetry`
snapshot upward every tick.

Movement is fully deterministic given the graph's live congestion state: the
truck reads each edge's ``effective_speed_kmh`` and integrates position over one
tick, possibly crossing several short edges in a single step.  All stochasticity
lives in the *environment*, never in the actuator -- which keeps the agent unit
testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import TICK_HOURS, TICK_MINUTES, LOW_FUEL_PCT, LOW_WATER_FRACTION
from .enums import CapacityClass, OperationalStatus
from .topology import TransitGraph


# --------------------------------------------------------------------------- #
# Value objects                                                               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Telemetry:
    """Immutable per-tick snapshot pushed to the Central Coordinator."""

    truck_id: str
    capacity_class: str
    status: str
    current_node: str
    target_node: Optional[str]
    x: float
    y: float
    water_level_litres: float
    water_fraction: float
    fuel_energy_pct: float
    speed_kmh: float
    mission_id: Optional[str]


@dataclass
class MoveResult:
    """Outcome of a single :meth:`TankerTruck.advance` integration step."""

    moved_km: float
    arrived: bool
    loitering: bool
    speed_kmh: float
    current_edge: Optional[tuple] = None


# --------------------------------------------------------------------------- #
# Agent                                                                        #
# --------------------------------------------------------------------------- #
@dataclass
class TankerTruck:
    """A single anti-smog misting tanker.

    Required state (per the brief) plus the bookkeeping needed to execute a
    multi-hop route, stagger arrivals and participate in the closed-loop supply
    lifecycle.
    """

    truck_id: str
    capacity_class: CapacityClass
    current_node: str
    water_level_liters: float
    fuel_energy_pct: float = 100.0
    current_speed_kmh: float = 0.0
    target_node: Optional[str] = None
    operational_status: OperationalStatus = OperationalStatus.IDLE

    # --- route execution ------------------------------------------------ #
    route: list[str] = field(default_factory=list)
    route_index: int = 0           # currently traversing route[i] -> route[i+1]
    edge_progress_km: float = 0.0   # distance covered along the current edge
    x: float = 0.0
    y: float = 0.0

    # --- mission / coordination bookkeeping ----------------------------- #
    mission_id: Optional[str] = None          # hotspot node id being serviced
    route_purpose: str = "IDLE"               # MISSION | REPLENISH_WATER | REPLENISH_FUEL
    planned_delivery_liters: float = 0.0      # this truck's share of V_req
    hold_until_tick: int = 0                  # ETA-sync loiter gate
    console_locked: bool = False              # AI has overridden the in-cab route
    stationary_misting: bool = False          # in-hotspot trapped curtain mode
    stuck_edge: Optional[tuple] = None        # segment that trapped this truck
    stuck_since_tick: int = -1                # tick the truck entered STUCK
    last_event: str = ""                      # latest notable event (dashboard)

    # ================================================================== #
    # Derived quantities                                                  #
    # ================================================================== #
    @property
    def max_water_liters(self) -> float:
        """Tank capacity for this class (L)."""
        return float(self.capacity_class.litres)

    @property
    def water_fraction(self) -> float:
        """Water level as a fraction of capacity in ``[0, 1]``."""
        return self.water_level_liters / self.max_water_liters

    @property
    def spray_rate_lpm(self) -> float:
        """Cannon throughput for this class (L/min)."""
        return self.capacity_class.spray_rate_lpm

    @property
    def is_low_water(self) -> bool:
        """``True`` when below the 15 % forced-replenishment floor."""
        return self.water_fraction < LOW_WATER_FRACTION

    @property
    def is_low_fuel(self) -> bool:
        """``True`` when below the 20 % forced-refuel floor."""
        return self.fuel_energy_pct < LOW_FUEL_PCT

    @property
    def is_available(self) -> bool:
        """Eligible for new hotspot tasking (idle and adequately supplied)."""
        return (
            self.operational_status == OperationalStatus.IDLE
            and not self.is_low_water
            and not self.is_low_fuel
        )

    @property
    def spray_capacity_per_tick(self) -> float:
        """Litres this truck can atomise in one full spraying tick."""
        return self.spray_rate_lpm * TICK_MINUTES

    # ================================================================== #
    # Command surface (driven by the Central AI)                          #
    # ================================================================== #
    def assign_route(
        self,
        route: list[str],
        target: str,
        *,
        purpose: str,
        mission_id: Optional[str] = None,
        planned_delivery: float = 0.0,
        hold_until_tick: int = 0,
        console_locked: bool = False,
    ) -> None:
        """Load a new AI-computed route and switch the truck EN_ROUTE.

        Resets edge progress; ``route[0]`` is expected to equal the truck's
        current node.  A non-zero ``hold_until_tick`` makes the truck *loiter*
        until that tick before departing (the mechanism behind staggered,
        synchronised arrivals).
        """
        self.route = list(route)
        self.route_index = 0
        self.edge_progress_km = 0.0
        self.target_node = target
        self.route_purpose = purpose
        self.mission_id = mission_id
        self.planned_delivery_liters = planned_delivery
        self.hold_until_tick = hold_until_tick
        self.console_locked = console_locked
        self.stationary_misting = False
        self.operational_status = OperationalStatus.EN_ROUTE

    def reset_to_idle(self, current_node: Optional[str] = None) -> None:
        """Clear all assignment state and return the truck to the IDLE pool."""
        if current_node is not None:
            self.current_node = current_node
        self.route = []
        self.route_index = 0
        self.edge_progress_km = 0.0
        self.target_node = None
        self.route_purpose = "IDLE"
        self.mission_id = None
        self.planned_delivery_liters = 0.0
        self.hold_until_tick = 0
        self.console_locked = False
        self.stationary_misting = False
        self.stuck_edge = None
        self.stuck_since_tick = -1
        self.current_speed_kmh = 0.0
        self.operational_status = OperationalStatus.IDLE

    # ================================================================== #
    # Kinematics                                                          #
    # ================================================================== #
    def sync_position(self, graph: TransitGraph) -> None:
        """Recompute planar ``(x, y)`` from the current edge + progress."""
        if not self.route or self.route_index >= len(self.route) - 1:
            node = graph.node(self.current_node)
            self.x, self.y = node.x, node.y
            return
        u = graph.node(self.route[self.route_index])
        v = graph.node(self.route[self.route_index + 1])
        edge = graph.edge(u.node_id, v.node_id)
        frac = 0.0 if edge.distance_km == 0 else self.edge_progress_km / edge.distance_km
        self.x = u.x + (v.x - u.x) * frac
        self.y = u.y + (v.y - u.y) * frac

    def advance(self, graph: TransitGraph, current_tick: int) -> MoveResult:
        """Integrate one tick of motion along the assigned route.

        Honours the ETA-sync loiter gate, then greedily consumes the tick's
        time budget across as many edges as the live effective speeds permit.
        The *reported* speed is that of the first (binding) edge at tick start,
        which is what the coordinator inspects for the < 5 km/h STUCK anomaly.
        """
        if self.operational_status != OperationalStatus.EN_ROUTE:
            return MoveResult(0.0, arrived=False, loitering=False, speed_kmh=0.0)

        # Already at destination -> immediate arrival.
        if not self.route or self.route_index >= len(self.route) - 1:
            self.current_speed_kmh = 0.0
            return MoveResult(0.0, arrived=True, loitering=False, speed_kmh=0.0)

        # ETA synchronisation: hold position until the scheduled departure tick.
        if current_tick < self.hold_until_tick:
            self.current_speed_kmh = 0.0
            self.sync_position(graph)
            edge = (self.route[self.route_index], self.route[self.route_index + 1])
            return MoveResult(0.0, arrived=False, loitering=True, speed_kmh=0.0, current_edge=edge)

        budget_hours = TICK_HOURS
        moved_km = 0.0
        reported_speed: Optional[float] = None
        arrived = False
        binding_edge = (self.route[self.route_index], self.route[self.route_index + 1])

        while budget_hours > 1e-9 and self.route_index < len(self.route) - 1:
            u = self.route[self.route_index]
            v = self.route[self.route_index + 1]
            edge = graph.edge(u, v)
            eff_speed = edge.effective_speed_kmh()
            if reported_speed is None:
                reported_speed = eff_speed  # speed experienced on the current edge

            edge_remaining = edge.distance_km - self.edge_progress_km
            time_to_finish = edge_remaining / eff_speed if eff_speed > 0 else float("inf")

            if time_to_finish <= budget_hours:
                # Finish this edge and roll onto the next node.
                moved_km += edge_remaining
                self._consume_fuel_for_distance(edge_remaining)
                budget_hours -= time_to_finish
                self.route_index += 1
                self.edge_progress_km = 0.0
                self.current_node = v
                if v == self.target_node or self.route_index >= len(self.route) - 1:
                    arrived = True
                    break
            else:
                # Partial progress along the current edge.
                step_km = eff_speed * budget_hours
                self.edge_progress_km += step_km
                moved_km += step_km
                self._consume_fuel_for_distance(step_km)
                budget_hours = 0.0

        self.current_speed_kmh = reported_speed if reported_speed is not None else 0.0
        self.sync_position(graph)
        return MoveResult(
            moved_km=moved_km,
            arrived=arrived,
            loitering=False,
            speed_kmh=self.current_speed_kmh,
            current_edge=binding_edge,
        )

    # ================================================================== #
    # Consumables                                                         #
    # ================================================================== #
    def _consume_fuel_for_distance(self, km: float) -> None:
        """Burn traction energy proportional to distance travelled."""
        self.fuel_energy_pct = max(
            0.0, self.fuel_energy_pct - km * self.capacity_class.fuel_burn_per_km
        )

    def burn_idle_fuel(self, pct: float) -> None:
        """Burn auxiliary energy (genset/AC/cannon) while not translating."""
        self.fuel_energy_pct = max(0.0, self.fuel_energy_pct - pct)

    def spray(self, efficiency: float = 1.0) -> float:
        """Atomise water for one tick; returns litres actually dispensed.

        ``efficiency`` < 1 models the reduced footprint of a *stationary*
        in-gridlock misting curtain versus open-area spraying.
        """
        dispensed = min(self.water_level_liters, self.spray_capacity_per_tick * efficiency)
        self.water_level_liters = max(0.0, self.water_level_liters - dispensed)
        return dispensed

    def refill_water(self, litres: float) -> float:
        """Take on recycled water (clamped at capacity); returns litres accepted."""
        room = self.max_water_liters - self.water_level_liters
        accepted = min(room, litres)
        self.water_level_liters += accepted
        return accepted

    def recharge_fuel(self, pct: float) -> float:
        """Restore energy (clamped at 100 %); returns the points actually added."""
        room = 100.0 - self.fuel_energy_pct
        added = min(room, pct)
        self.fuel_energy_pct += added
        return added

    # ================================================================== #
    # Telemetry                                                           #
    # ================================================================== #
    def telemetry(self) -> Telemetry:
        """Build the immutable snapshot reported to the coordinator each tick."""
        return Telemetry(
            truck_id=self.truck_id,
            capacity_class=self.capacity_class.name,
            status=self.operational_status.value,
            current_node=self.current_node,
            target_node=self.target_node,
            x=round(self.x, 2),
            y=round(self.y, 2),
            water_level_litres=round(self.water_level_liters, 1),
            water_fraction=round(self.water_fraction, 3),
            fuel_energy_pct=round(self.fuel_energy_pct, 1),
            speed_kmh=round(self.current_speed_kmh, 1),
            mission_id=self.mission_id,
        )
