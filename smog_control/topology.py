"""
Network topology: the directed graph ``G = (V, E)`` of Delhi's transit topology.

Vertices (:class:`Node`) carry *dynamic* air-quality and traffic telemetry plus
static 2-D coordinates (used both for the localised-hotspot geometry test and as
a sanity anchor for segment distances).  Two specialised subclasses model the
closed-loop supply infrastructure:

* :class:`SewageTreatmentPlantNode` -- recycled water source (STP).
* :class:`RefuelingStationNode`     -- CNG / EV charging source.

Edges (:class:`Edge`) are *stateful*: their ``traffic_density_factor`` and
``emission_penalty`` mutate every tick, which is precisely what turns plain
Dijkstra into the dynamic, multi-objective router required by the brief.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Iterator, Optional

from .config import (
    AQI_AMBIENT_DRIFT,
    AQI_INFLUX_COEF,
    CRITICAL_PM25,
    DEFAULT_REFUEL_PCT_PER_MIN,
    DEFAULT_STP_DISPENSE_LPM,
    REPLENISH_TARGET_FRACTION,
    TICK_MINUTES,
    TRAFFIC_FACTOR_MAX,
    TRAFFIC_FACTOR_MIN,
)
from .enums import AQICategory, NodeType


# --------------------------------------------------------------------------- #
# Vertices                                                                     #
# --------------------------------------------------------------------------- #
@dataclass
class Node:
    """A junction in the transit graph with live AQI / traffic telemetry.

    Attributes
    ----------
    node_id:
        Stable machine identifier (used as graph key).
    name:
        Human-readable label (e.g. ``"Anand Vihar"``).
    x, y:
        Planar coordinates in kilometres on a local Delhi grid.  Used for the
        "is the truck physically inside the pollution zone" geometry test and
        as a fallback distance anchor.
    current_AQI_PM25:
        Live PM2.5 concentration (ug/m3) -- a *dynamic* node attribute.
    traffic_rate_influx:
        Live vehicle-influx index (1.0 = nominal) -- a *dynamic* node attribute
        and the leading indicator the predictive engine differentiates.
    radius_km:
        Radius of the localised pollution "zone" around this node; a tanker
        inside this radius is treated as on-site for stationary-misting logic.
    """

    node_id: str
    name: str
    x: float
    y: float
    node_type: NodeType = NodeType.JUNCTION
    current_AQI_PM25: float = 80.0
    traffic_rate_influx: float = 1.0
    radius_km: float = 1.6
    # Optional real-world geography (set when nodes are real metro stations).
    lat: Optional[float] = None
    lng: Optional[float] = None
    line: str = ""            # metro line this node primarily belongs to

    # Rolling telemetry history (most-recent-last) for trend analytics.
    aqi_history: deque = field(default_factory=lambda: deque(maxlen=8))
    influx_history: deque = field(default_factory=lambda: deque(maxlen=8))

    # ------------------------------------------------------------------ #
    # Telemetry bookkeeping                                               #
    # ------------------------------------------------------------------ #
    def snapshot_history(self) -> None:
        """Append the current AQI / influx readings to the rolling buffers.

        Called once per tick *before* mutation so the predictive engine can
        differentiate consecutive samples.
        """
        self.aqi_history.append(self.current_AQI_PM25)
        self.influx_history.append(self.traffic_rate_influx)

    def influx_n_ticks_ago(self, n: int) -> Optional[float]:
        """Return the influx reading ``n`` ticks ago, or ``None`` if too short."""
        if len(self.influx_history) <= n:
            return None
        return self.influx_history[-(n + 1)]

    # ------------------------------------------------------------------ #
    # Air-quality dynamics                                                #
    # ------------------------------------------------------------------ #
    def accrue_pollution(self) -> None:
        """Advance the passive AQI model by one tick.

        Mathematical model (per tick)::

            dAQI = AMBIENT_DRIFT + INFLUX_COEF * traffic_rate_influx

        i.e. a constant regional-haze drift plus a term proportional to the
        live vehicular influx feeding tail-pipe PM2.5 into the cell.
        """
        self.current_AQI_PM25 += AQI_AMBIENT_DRIFT + AQI_INFLUX_COEF * self.traffic_rate_influx

    def knock_down_aqi(self, micrograms: float) -> float:
        """Reduce AQI by ``micrograms`` (clamped at 0).  Returns the actual drop."""
        before = self.current_AQI_PM25
        self.current_AQI_PM25 = max(0.0, self.current_AQI_PM25 - micrograms)
        return before - self.current_AQI_PM25

    # ------------------------------------------------------------------ #
    # Geometry / classification helpers                                  #
    # ------------------------------------------------------------------ #
    def distance_to(self, x: float, y: float) -> float:
        """Euclidean distance (km) from this node to an arbitrary point."""
        return math.hypot(self.x - x, self.y - y)

    def contains_point(self, x: float, y: float) -> bool:
        """``True`` if point ``(x, y)`` lies inside this node's pollution zone."""
        return self.distance_to(x, y) <= self.radius_km

    @property
    def aqi_category(self) -> AQICategory:
        """Current CPCB band for this node."""
        return AQICategory.classify(self.current_AQI_PM25)

    @property
    def is_critical(self) -> bool:
        """``True`` when the live PM2.5 exceeds the actionable hotspot threshold."""
        return self.current_AQI_PM25 >= CRITICAL_PM25

    @property
    def is_infrastructure(self) -> bool:
        """``True`` for STP / refuelling service nodes."""
        return self.node_type in (NodeType.STP, NodeType.REFUELING)


class ServiceNode(Node, ABC):
    """Abstract base for replenishment infrastructure a tanker can dock at.

    Concrete facilities (STP, refuelling station) implement a single polymorphic
    :meth:`service` step plus a :meth:`is_satisfied` predicate, so the
    coordinator's closed-loop lifecycle is free of ``isinstance`` branching --
    it simply docks a truck and calls ``service`` until ``is_satisfied``.
    """

    @property
    @abstractmethod
    def replenish_purpose(self) -> str:
        """The truck ``route_purpose`` this facility fulfils."""

    @abstractmethod
    def service(self, truck: "object") -> tuple:
        """Serve one tick. Returns ``(amount_added, ledger_key)`` for billing."""

    @abstractmethod
    def is_satisfied(self, truck: "object") -> bool:
        """``True`` once the docked truck has reached its replenishment target."""


@dataclass
class SewageTreatmentPlantNode(ServiceNode):
    """STP vertex supplying *recycled* water to tankers.

    Models a finite reservoir drained by ``water_dispense_lpm`` while a tanker
    is docked, demonstrating the recycled-water circular-economy angle.
    """

    water_dispense_lpm: float = DEFAULT_STP_DISPENSE_LPM
    recycled_reserve_litres: float = 750_000.0

    def __post_init__(self) -> None:
        self.node_type = NodeType.STP

    @property
    def replenish_purpose(self) -> str:
        return "REPLENISH_WATER"

    def dispense(self, requested_litres: float) -> float:
        """Pump up to ``requested_litres`` of recycled water for one tick.

        Throughput is capped by both the per-minute pump rate (scaled to the
        tick length) and the remaining reservoir.
        """
        per_tick_cap = self.water_dispense_lpm * TICK_MINUTES
        served = min(requested_litres, per_tick_cap, self.recycled_reserve_litres)
        self.recycled_reserve_litres -= served
        return served

    def service(self, truck: "object") -> tuple:
        need = truck.max_water_liters - truck.water_level_liters
        accepted = truck.refill_water(self.dispense(need))
        return accepted, "water_l"

    def is_satisfied(self, truck: "object") -> bool:
        return truck.water_fraction >= REPLENISH_TARGET_FRACTION


@dataclass
class RefuelingStationNode(ServiceNode):
    """CNG / EV charging vertex restoring tanker energy."""

    refuel_pct_per_min: float = DEFAULT_REFUEL_PCT_PER_MIN
    fuel_kind: str = "CNG"

    def __post_init__(self) -> None:
        self.node_type = NodeType.REFUELING

    @property
    def replenish_purpose(self) -> str:
        return "REPLENISH_FUEL"

    def replenish(self, requested_pct: float) -> float:
        """Restore up to ``requested_pct`` energy points in one tick."""
        per_tick_cap = self.refuel_pct_per_min * TICK_MINUTES
        return min(requested_pct, per_tick_cap)

    def service(self, truck: "object") -> tuple:
        need = 100.0 - truck.fuel_energy_pct
        added = truck.recharge_fuel(self.replenish(need))
        return added, "fuel_pct"

    def is_satisfied(self, truck: "object") -> bool:
        return truck.fuel_energy_pct >= REPLENISH_TARGET_FRACTION * 100.0


# --------------------------------------------------------------------------- #
# Edges                                                                        #
# --------------------------------------------------------------------------- #
@dataclass
class Edge:
    """A directed, *stateful* road segment ``u -> v``.

    The brief's cost function is::

        W(e) = (distance_km / base_speed) * traffic_density_factor + emission_penalty

    The first term is free-flow travel time in hours, stretched by live
    congestion; the second is the dynamic AI-computed idling/emission overhead
    (filled in by the router, since it depends on the *vehicle class* and the
    destination cell's AQI).
    """

    source: str
    target: str
    distance_km: float
    base_speed: float                      # free-flow design speed (km/h)
    traffic_density_factor: float = 1.0    # 1.0 free-flow ... 5.0 gridlock (8 cap)
    emission_penalty: float = 0.0          # last AI-applied overhead (cost-hours)
    line: str = ""                         # metro corridor this segment follows
    line_color: str = ""                   # hex colour for map rendering
    geometry: list = field(default_factory=list)  # road-following [lat,lng] polyline

    factor_history: deque = field(default_factory=lambda: deque(maxlen=8))

    # ------------------------------------------------------------------ #
    def snapshot_history(self) -> None:
        """Record the current congestion factor for trend differentiation."""
        self.factor_history.append(self.traffic_density_factor)

    def factor_n_ticks_ago(self, n: int) -> Optional[float]:
        """Congestion factor ``n`` ticks ago, or ``None`` if history too short."""
        if len(self.factor_history) <= n:
            return None
        return self.factor_history[-(n + 1)]

    def set_factor(self, value: float) -> None:
        """Set the congestion factor, clamped to the physical [1.0, 8.0] band."""
        self.traffic_density_factor = max(
            TRAFFIC_FACTOR_MIN, min(TRAFFIC_FACTOR_MAX, value)
        )

    # ------------------------------------------------------------------ #
    def effective_speed_kmh(self) -> float:
        """Realised speed under congestion = ``base_speed / traffic_factor``."""
        return self.base_speed / self.traffic_density_factor

    def travel_time_hours(self) -> float:
        """First term of W(e): congestion-stretched free-flow travel time (h)."""
        return (self.distance_km / self.base_speed) * self.traffic_density_factor

    def base_weight(self) -> float:
        """Travel-time component of the edge weight (cost-hours, no penalty)."""
        return self.travel_time_hours()

    @property
    def key(self) -> tuple:
        """``(source, target)`` adjacency key."""
        return (self.source, self.target)


# --------------------------------------------------------------------------- #
# Graph container                                                              #
# --------------------------------------------------------------------------- #
class TransitGraph:
    """Adjacency-list directed graph with O(1) node/edge lookup.

    The container owns the authoritative node and edge objects; agents hold only
    string identifiers and dereference through here, keeping a single source of
    truth for shared mutable state.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: dict[tuple, Edge] = {}
        self._adjacency: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ #
    # Construction                                                        #
    # ------------------------------------------------------------------ #
    def add_node(self, node: Node) -> Node:
        """Register a vertex (idempotent on ``node_id``)."""
        self._nodes[node.node_id] = node
        self._adjacency.setdefault(node.node_id, [])
        return node

    def add_edge(self, edge: Edge, *, bidirectional: bool = True) -> None:
        """Register a road segment; mirrors it back by default.

        Real arterials carry traffic both ways, so we instantiate an
        *independent* reverse :class:`Edge` (its own congestion state) unless the
        caller explicitly requests a one-way link.
        """
        if edge.source not in self._nodes or edge.target not in self._nodes:
            raise KeyError(f"Edge {edge.key} references an unknown node")
        self._edges[edge.key] = edge
        self._adjacency[edge.source].append(edge.target)
        if bidirectional:
            reverse = Edge(
                source=edge.target,
                target=edge.source,
                distance_km=edge.distance_km,
                base_speed=edge.base_speed,
                traffic_density_factor=edge.traffic_density_factor,
            )
            self._edges[reverse.key] = reverse
            self._adjacency[edge.target].append(edge.source)

    # ------------------------------------------------------------------ #
    # Accessors                                                           #
    # ------------------------------------------------------------------ #
    def node(self, node_id: str) -> Node:
        """Return the node object for ``node_id`` (raises if absent)."""
        return self._nodes[node_id]

    def edge(self, source: str, target: str) -> Edge:
        """Return the directed edge ``source -> target`` (raises if absent)."""
        return self._edges[(source, target)]

    def has_edge(self, source: str, target: str) -> bool:
        """``True`` if a directed edge ``source -> target`` exists."""
        return (source, target) in self._edges

    def neighbors(self, node_id: str) -> list[str]:
        """Out-neighbour ids of ``node_id``."""
        return self._adjacency.get(node_id, [])

    def nodes(self) -> Iterator[Node]:
        """Iterate over all node objects."""
        return iter(self._nodes.values())

    def edges(self) -> Iterator[Edge]:
        """Iterate over all directed edge objects."""
        return iter(self._edges.values())

    def node_ids(self) -> Iterable[str]:
        """All vertex identifiers."""
        return self._nodes.keys()

    def nodes_of_type(self, node_type: NodeType) -> list[Node]:
        """All nodes whose role matches ``node_type`` (e.g. every STP)."""
        return [n for n in self._nodes.values() if n.node_type == node_type]

    # ------------------------------------------------------------------ #
    # Per-tick maintenance                                                #
    # ------------------------------------------------------------------ #
    def snapshot_all_history(self) -> None:
        """Push current readings of every node and edge into their buffers."""
        for node in self._nodes.values():
            node.snapshot_history()
        for edge in self._edges.values():
            edge.snapshot_history()

    def __len__(self) -> int:
        return len(self._nodes)
