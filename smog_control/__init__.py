"""
Agentic AI Pollution-Control System -- Delhi anti-smog tanker network.

A decentralised multi-agent simulation in which a Central AI Coordinator routes a
fleet of IoT-equipped water-tanker trucks (anti-smog misting cannons) across
Delhi's transit topology using a modified, dynamic, multi-objective Dijkstra
solver.

Public API
----------
>>> from smog_control import SimulationEngine
>>> SimulationEngine(seed=7).run_ticks(12)
"""

from __future__ import annotations

from .config import TICK_MINUTES
from .coordinator import CentralAICoordinator, Mission
from .dispatch import CandidateScore, FleetDispatcher, SyncSlot
from .engine import SimulationEngine
from .enums import AQICategory, CapacityClass, NodeType, OperationalStatus
from .routing import MultiObjectiveRouter, Route
from .topology import (
    Edge,
    Node,
    RefuelingStationNode,
    ServiceNode,
    SewageTreatmentPlantNode,
    TransitGraph,
)
from .trucks import MoveResult, TankerTruck, Telemetry

__all__ = [
    "SimulationEngine",
    "CentralAICoordinator",
    "Mission",
    "FleetDispatcher",
    "CandidateScore",
    "SyncSlot",
    "MultiObjectiveRouter",
    "Route",
    "TankerTruck",
    "Telemetry",
    "MoveResult",
    "TransitGraph",
    "Node",
    "Edge",
    "ServiceNode",
    "SewageTreatmentPlantNode",
    "RefuelingStationNode",
    "OperationalStatus",
    "CapacityClass",
    "NodeType",
    "AQICategory",
    "TICK_MINUTES",
]

__version__ = "1.0.0"
