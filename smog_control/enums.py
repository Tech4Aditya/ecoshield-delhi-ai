"""
Strongly-typed enumerations shared across the simulation.

Using :class:`enum.Enum` (instead of bare strings) gives us exhaustive,
self-documenting state machines for truck lifecycle, vehicle sizing, node roles
and air-quality banding -- all of which the type checker can reason about.
"""

from __future__ import annotations

from enum import Enum


class OperationalStatus(Enum):
    """Finite-state lifecycle of a mobile tanker truck.

    Legal transitions (enforced informally by the coordinator)::

        IDLE        -> EN_ROUTE | REPLENISHING
        EN_ROUTE    -> SPRAYING | STUCK | REPLENISHING | IDLE
        SPRAYING    -> IDLE | REPLENISHING | STUCK
        STUCK       -> IDLE | EN_ROUTE          (once gridlock clears / re-tasked)
        REPLENISHING-> IDLE                      (once fluid/charge >= 95 %)
    """

    IDLE = "IDLE"
    EN_ROUTE = "EN_ROUTE"
    SPRAYING = "SPRAYING"
    STUCK = "STUCK"
    REPLENISHING = "REPLENISHING"


class CapacityClass(Enum):
    """Tanker sizing class.

    The enum *value* is the on-board water capacity in litres, while derived
    properties expose class-dependent physics (emission weight, spray rate and
    fuel burn) so the rest of the code never hard-codes per-class numbers.
    """

    MINI = 3000
    MEDIUM = 5000
    HEAVY = 12000

    # ------------------------------------------------------------------ #
    @property
    def litres(self) -> int:
        """Maximum on-board recycled-water capacity (L)."""
        return self.value

    @property
    def emission_weight(self) -> float:
        """Relative tail-pipe footprint while idling (dimensionless).

        Heavier chassis emit disproportionately more when forced to idle, so
        the multi-objective router penalises routing them through gridlocked,
        already-critical AQI cells.
        """
        return {"MINI": 1.0, "MEDIUM": 1.6, "HEAVY": 2.5}[self.name]

    @property
    def spray_rate_lpm(self) -> float:
        """Anti-smog cannon atomisation throughput (litres / minute)."""
        return {"MINI": 250.0, "MEDIUM": 450.0, "HEAVY": 750.0}[self.name]

    @property
    def fuel_burn_per_km(self) -> float:
        """Traction energy burn (percentage points of tank per km)."""
        return {"MINI": 0.20, "MEDIUM": 0.32, "HEAVY": 0.55}[self.name]

    @property
    def label(self) -> str:
        """Human-readable ``"Heavy (12000L)"`` style label."""
        return f"{self.name.title()} ({self.litres}L)"


class NodeType(Enum):
    """Role a graph vertex plays in the transit topology."""

    JUNCTION = "JUNCTION"          # ordinary traffic / pollution junction
    STP = "STP"                    # Sewage Treatment Plant (recycled water)
    REFUELING = "REFUELING"        # CNG / EV charging infrastructure


class AQICategory(Enum):
    """CPCB-style PM2.5 banding.

    Each member carries ``(rank, lower_bound, glyph)`` so the dashboard can
    colour/annotate cells and the coordinator can reason ordinally about
    severity via :pyattr:`rank`.
    """

    GOOD = (0, 0.0, "*")
    SATISFACTORY = (1, 30.0, "+")
    MODERATE = (2, 60.0, "~")
    POOR = (3, 90.0, "!")
    VERY_POOR = (4, 120.0, "!!")
    SEVERE = (5, 250.0, "XX")

    def __init__(self, rank: int, lower_bound: float, glyph: str) -> None:
        self.rank = rank
        self.lower_bound = lower_bound
        self.glyph = glyph

    # ------------------------------------------------------------------ #
    @classmethod
    def classify(cls, pm25: float) -> "AQICategory":
        """Return the band a PM2.5 reading falls into (highest matching bound)."""
        chosen = cls.GOOD
        for band in cls:
            if pm25 >= band.lower_bound:
                chosen = band
        return chosen

    @property
    def is_critical(self) -> bool:
        """``True`` for VERY_POOR and worse (actionable hotspot territory)."""
        return self.rank >= AQICategory.VERY_POOR.rank
