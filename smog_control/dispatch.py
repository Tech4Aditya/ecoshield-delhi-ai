"""
Fleet dispatching: the coordinated, multi-truck assignment solver.

This module turns a *volume requirement* ``V_req`` at a hotspot into a
*synchronised sub-fleet* of 2-3 tankers whose arrivals are staggered so that as
one tanker empties, the next rolls in -- maintaining a continuous mitigation
curtain.

Three stages:

1. :meth:`FleetDispatcher.efficiency_matrix` -- score every in-radius, available
   tanker against the hotspot on a weighted, multi-criteria objective.
2. :meth:`FleetDispatcher.select_subfleet` -- greedily pick the smallest high-
   scoring set whose combined water covers ``V_req`` (capped at 3).
3. :meth:`FleetDispatcher.synchronize_etas` -- compute per-truck loiter gates so
   arrivals dovetail with the preceding truck's spray-out time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .config import (
    MAX_DISPATCH_ETA_MIN,
    MAX_SUBFLEET,
    TICK_MINUTES,
    W_CLASS,
    W_ETA,
    W_FUEL,
    W_VOLUME,
)
from .enums import CapacityClass
from .routing import MultiObjectiveRouter, Route
from .trucks import TankerTruck


# --------------------------------------------------------------------------- #
# Scoring record                                                              #
# --------------------------------------------------------------------------- #
@dataclass
class CandidateScore:
    """One row of the Efficiency-Score Matrix (a truck evaluated for a hotspot)."""

    truck_id: str
    capacity_class: CapacityClass
    route: Route
    eta_min: float
    deliverable_liters: float
    fuel_pct: float
    class_suitability: float
    score: float

    @property
    def spray_capacity_per_tick(self) -> float:
        """Litres this candidate atomises per full spraying tick."""
        return self.capacity_class.spray_rate_lpm * TICK_MINUTES

    @property
    def spray_ticks(self) -> int:
        """Ticks needed to discharge ``deliverable_liters`` at full rate."""
        if self.spray_capacity_per_tick <= 0:
            return 1
        return max(1, math.ceil(self.deliverable_liters / self.spray_capacity_per_tick))


@dataclass
class SyncSlot:
    """A scheduled, time-synchronised dispatch order for one tanker."""

    candidate: CandidateScore
    hold_until_tick: int       # depart only at/after this tick (loiter gate)
    eta_ticks: int             # whole ticks of driving once departed
    arrival_tick: int          # projected on-site tick
    finish_tick: int           # projected spray-out tick


# --------------------------------------------------------------------------- #
# Dispatcher                                                                  #
# --------------------------------------------------------------------------- #
class FleetDispatcher:
    """Stateless solver coordinating sub-fleet selection and arrival staggering."""

    def __init__(self, router: MultiObjectiveRouter) -> None:
        self.router = router

    # ------------------------------------------------------------------ #
    # Stage 1 -- Efficiency-Score Matrix                                  #
    # ------------------------------------------------------------------ #
    def efficiency_matrix(
        self,
        fleet: list[TankerTruck],
        hotspot_id: str,
        v_req: float,
    ) -> list[CandidateScore]:
        """Score every viable, available tanker for servicing ``hotspot_id``.

        The weighted objective (higher == better) is::

            score = W_VOLUME * min(1, deliverable / V_req)      # coverage
                  + W_ETA    * 1 / (1 + eta_min / 30)           # responsiveness
                  + W_FUEL   * fuel_pct / 100                    # energy margin
                  + W_CLASS  * min(1, capacity / V_req)          # sizing fit

        Trucks with no path, an ETA beyond the viable radius, or insufficient
        fuel to survive the trip are excluded entirely.
        """
        matrix: list[CandidateScore] = []
        for truck in fleet:
            if not truck.is_available:
                continue
            route = self.router.shortest_path(
                truck.current_node, hotspot_id, truck.capacity_class
            )
            if route is None:
                continue
            eta = route.eta_minutes
            if eta > MAX_DISPATCH_ETA_MIN:
                continue  # outside the viable response radius

            # Reject if the round/one-way trip would strand the truck on empty.
            fuel_needed = route.total_distance_km * truck.capacity_class.fuel_burn_per_km
            if truck.fuel_energy_pct - fuel_needed < 5.0:
                continue

            deliverable = truck.water_level_liters
            class_suitability = min(1.0, truck.max_water_liters / max(v_req, 1.0))

            volume_term = W_VOLUME * min(1.0, deliverable / max(v_req, 1.0))
            eta_term = W_ETA * (1.0 / (1.0 + eta / 30.0))
            fuel_term = W_FUEL * (truck.fuel_energy_pct / 100.0)
            class_term = W_CLASS * class_suitability
            score = volume_term + eta_term + fuel_term + class_term

            matrix.append(
                CandidateScore(
                    truck_id=truck.truck_id,
                    capacity_class=truck.capacity_class,
                    route=route,
                    eta_min=eta,
                    deliverable_liters=deliverable,
                    fuel_pct=truck.fuel_energy_pct,
                    class_suitability=class_suitability,
                    score=score,
                )
            )

        matrix.sort(key=lambda c: c.score, reverse=True)
        return matrix

    # ------------------------------------------------------------------ #
    # Stage 2 -- Sub-fleet selection (workload splitting)                 #
    # ------------------------------------------------------------------ #
    def select_subfleet(
        self,
        matrix: list[CandidateScore],
        v_req: float,
        *,
        max_trucks: int = MAX_SUBFLEET,
    ) -> list[CandidateScore]:
        """Greedily choose the smallest high-scoring set covering ``V_req``.

        Iterates the score-sorted matrix accumulating deliverable water until the
        requirement is met or ``max_trucks`` is reached.  Returns whatever subset
        was assembled (possibly under-covering if the fleet is stretched -- the
        coordinator logs the shortfall).
        """
        selected: list[CandidateScore] = []
        cumulative = 0.0
        for cand in matrix:
            if len(selected) >= max_trucks:
                break
            selected.append(cand)
            cumulative += cand.deliverable_liters
            if cumulative >= v_req:
                break
        return selected

    # ------------------------------------------------------------------ #
    # Stage 3 -- ETA synchronisation (staggered arrivals)                 #
    # ------------------------------------------------------------------ #
    def synchronize_etas(
        self,
        subfleet: list[CandidateScore],
        current_tick: int,
    ) -> list[SyncSlot]:
        """Stagger departures so each tanker arrives as the previous empties.

        Sorted by ETA, the nearest truck departs immediately.  Every subsequent
        truck is given a *loiter gate* (``hold_until_tick``) chosen so its
        projected arrival coincides with the running spray-out time of the
        sub-fleet ahead of it::

            arrival[0]  = now + eta_ticks[0]
            finish[k-1] = arrival[k-1] + spray_ticks[k-1]
            hold[k]     = max(now, finish[k-1] - eta_ticks[k])
            arrival[k]  = hold[k] + eta_ticks[k]

        This yields a continuous mitigation curtain instead of a wasteful convoy
        that all arrives (and all empties) at once.
        """
        ordered = sorted(subfleet, key=lambda c: c.eta_min)
        slots: list[SyncSlot] = []
        prev_finish = current_tick

        for idx, cand in enumerate(ordered):
            eta_ticks = max(1, math.ceil(cand.eta_min / TICK_MINUTES))
            if idx == 0:
                hold_until = current_tick
            else:
                hold_until = max(current_tick, prev_finish - eta_ticks)
            arrival = hold_until + eta_ticks
            finish = arrival + cand.spray_ticks
            prev_finish = finish
            slots.append(
                SyncSlot(
                    candidate=cand,
                    hold_until_tick=hold_until,
                    eta_ticks=eta_ticks,
                    arrival_tick=arrival,
                    finish_tick=finish,
                )
            )
        return slots
