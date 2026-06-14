"""
Modified, dynamic, multi-objective Dijkstra routing.

Classic Dijkstra minimises a *static* additive edge weight.  Here the weight is
recomputed on demand from live edge/node telemetry **and** the requesting
vehicle's emission class:

    W(e, vehicle) = base_weight(e)          # congestion-stretched travel time
                  + emission_penalty(e, v, vehicle)

where the second term is non-zero only when a heavy chassis would be forced to
*idle* (high ``traffic_density_factor``) while crossing into an already-critical
AQI cell -- exactly the "secondary fleet emissions" the Central AI must avoid.

Because the penalty depends on the vehicle, two different tankers can receive two
different optimal paths over the *same* graph at the *same* instant -- the defining
property of the "modified" router.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Optional

from .config import (
    CRITICAL_PM25,
    EMISSION_PENALTY_COEF,
    IDLE_TRAFFIC_FACTOR,
)
from .enums import CapacityClass, NodeType
from .topology import Edge, Node, TransitGraph


# --------------------------------------------------------------------------- #
# Result object                                                               #
# --------------------------------------------------------------------------- #
@dataclass
class Route:
    """An optimal path plus its decomposed cost metrics.

    Attributes
    ----------
    path:
        Ordered list of node ids from source to target (inclusive).
    total_cost:
        The minimised objective (travel time + emission penalties), cost-hours.
    travel_time_hours:
        Pure congestion-stretched driving time along ``path`` (no penalties).
    total_distance_km:
        Physical length of ``path``.
    emission_overhead:
        The portion of ``total_cost`` attributable to idling-emission penalties.
    """

    path: list[str]
    total_cost: float
    travel_time_hours: float
    total_distance_km: float
    emission_overhead: float = 0.0

    # ------------------------------------------------------------------ #
    @property
    def eta_minutes(self) -> float:
        """Estimated time of arrival in minutes (driving time only)."""
        return self.travel_time_hours * 60.0

    @property
    def hop_count(self) -> int:
        """Number of edges traversed."""
        return max(0, len(self.path) - 1)

    @property
    def is_trivial(self) -> bool:
        """``True`` when source == target (already on-site)."""
        return len(self.path) <= 1

    def next_hop(self, current: str) -> Optional[str]:
        """Return the node immediately after ``current`` on the path."""
        try:
            idx = self.path.index(current)
        except ValueError:
            return None
        if idx + 1 < len(self.path):
            return self.path[idx + 1]
        return None

    def describe(self) -> str:
        """Compact ``A -> B -> C`` rendering for the dashboard."""
        return " -> ".join(self.path) if self.path else "(no path)"


# --------------------------------------------------------------------------- #
# Router                                                                       #
# --------------------------------------------------------------------------- #
class MultiObjectiveRouter:
    """Dynamic, vehicle-aware shortest-path engine over a :class:`TransitGraph`.

    Stateless apart from its graph reference, so a single instance is shared by
    the coordinator and is safe to call repeatedly within a tick.
    """

    def __init__(self, graph: TransitGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------ #
    # Cost function                                                       #
    # ------------------------------------------------------------------ #
    def emission_penalty(self, edge: Edge, dest: Node, vehicle: Optional[CapacityClass]) -> float:
        """Dynamic idling-emission overhead for crossing ``edge`` into ``dest``.

        Mathematical definition::

            severity = max(0, (AQI_dest - CRITICAL_PM25) / CRITICAL_PM25)
            penalty  = COEF * emission_weight(vehicle) * traffic_factor * severity
                       if traffic_factor >= IDLE_TRAFFIC_FACTOR and dest critical
                       else 0

        Intuition: a tanker only pollutes meaningfully when it *crawls* (idles)
        through a cell that is already choking.  The penalty is proportional to
        how badly the cell is breached and how heavy the chassis is, expressed as
        an equivalent travel-time overhead so it is additive with ``base_weight``.
        """
        if vehicle is None:
            weight = 1.0
        else:
            weight = vehicle.emission_weight

        if edge.traffic_density_factor < IDLE_TRAFFIC_FACTOR:
            return 0.0
        if dest.current_AQI_PM25 < CRITICAL_PM25:
            return 0.0

        severity = (dest.current_AQI_PM25 - CRITICAL_PM25) / CRITICAL_PM25
        return EMISSION_PENALTY_COEF * weight * edge.traffic_density_factor * severity

    def edge_weight(self, edge: Edge, vehicle: Optional[CapacityClass]) -> tuple[float, float]:
        """Return ``(total_weight, emission_component)`` for one edge.

        Also caches the emission component back onto the edge so the dashboard
        can surface *why* a route bent around a particular segment.
        """
        dest = self.graph.node(edge.target)
        penalty = self.emission_penalty(edge, dest, vehicle)
        edge.emission_penalty = penalty
        return edge.base_weight() + penalty, penalty

    # ------------------------------------------------------------------ #
    # Core Dijkstra                                                       #
    # ------------------------------------------------------------------ #
    def _dijkstra(
        self, source: str, vehicle: Optional[CapacityClass]
    ) -> tuple[dict[str, float], dict[str, Optional[str]]]:
        """Single-source shortest paths via a binary heap.

        Returns ``(dist, prev)`` maps over all reachable nodes, where ``dist``
        holds the minimised multi-objective cost and ``prev`` the predecessor
        pointers for path reconstruction.  Complexity ``O((V + E) log V)``.
        """
        dist: dict[str, float] = {source: 0.0}
        prev: dict[str, Optional[str]] = {source: None}
        visited: set[str] = set()
        # Heap entries: (cumulative_cost, node_id)
        heap: list[tuple[float, str]] = [(0.0, source)]

        while heap:
            cost_u, u = heapq.heappop(heap)
            if u in visited:
                continue
            visited.add(u)

            for v in self.graph.neighbors(u):
                if v in visited:
                    continue
                edge = self.graph.edge(u, v)
                w, _penalty = self.edge_weight(edge, vehicle)
                new_cost = cost_u + w
                if new_cost < dist.get(v, float("inf")):
                    dist[v] = new_cost
                    prev[v] = u
                    heapq.heappush(heap, (new_cost, v))

        return dist, prev

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #
    def shortest_path(
        self,
        source: str,
        target: str,
        vehicle: Optional[CapacityClass] = None,
    ) -> Optional[Route]:
        """Compute the optimal :class:`Route` from ``source`` to ``target``.

        Returns ``None`` if ``target`` is unreachable.  A trivial (zero-length)
        route is returned when ``source == target``.
        """
        if source == target:
            return Route(path=[source], total_cost=0.0, travel_time_hours=0.0,
                         total_distance_km=0.0, emission_overhead=0.0)

        dist, prev = self._dijkstra(source, vehicle)
        if target not in dist:
            return None

        path = self._reconstruct(prev, target)
        travel_time, distance, emission = self._decompose(path, vehicle)
        return Route(
            path=path,
            total_cost=dist[target],
            travel_time_hours=travel_time,
            total_distance_km=distance,
            emission_overhead=emission,
        )

    def nearest_facility(
        self,
        source: str,
        node_type: NodeType,
        vehicle: Optional[CapacityClass] = None,
    ) -> Optional[Route]:
        """Lowest-weight route from ``source`` to the closest node of ``node_type``.

        Used by the closed-loop supply lifecycle to find the cheapest STP /
        refuelling station once a tanker drops below its fluid/energy floor.
        """
        dist, prev = self._dijkstra(source, vehicle)
        best_target: Optional[str] = None
        best_cost = float("inf")
        for node in self.graph.nodes_of_type(node_type):
            cost = dist.get(node.node_id, float("inf"))
            if cost < best_cost:
                best_cost = cost
                best_target = node.node_id

        if best_target is None:
            return None
        if best_target == source:
            return Route(path=[source], total_cost=0.0, travel_time_hours=0.0,
                         total_distance_km=0.0, emission_overhead=0.0)

        path = self._reconstruct(prev, best_target)
        travel_time, distance, emission = self._decompose(path, vehicle)
        return Route(
            path=path,
            total_cost=best_cost,
            travel_time_hours=travel_time,
            total_distance_km=distance,
            emission_overhead=emission,
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _reconstruct(prev: dict[str, Optional[str]], target: str) -> list[str]:
        """Walk predecessor pointers back from ``target`` to the source."""
        path: list[str] = []
        cursor: Optional[str] = target
        while cursor is not None:
            path.append(cursor)
            cursor = prev.get(cursor)
        path.reverse()
        return path

    def _decompose(
        self, path: list[str], vehicle: Optional[CapacityClass]
    ) -> tuple[float, float, float]:
        """Sum travel time, distance and emission overhead along ``path``."""
        travel_time = 0.0
        distance = 0.0
        emission = 0.0
        for u, v in zip(path, path[1:]):
            edge = self.graph.edge(u, v)
            travel_time += edge.base_weight()
            distance += edge.distance_km
            emission += self.emission_penalty(edge, self.graph.node(v), vehicle)
        return travel_time, distance, emission
