"""
Unit + integration tests for the Agentic AI Pollution-Control System.

Run from the project root:

    python3 -m unittest discover -s tests -t . -v

Uses only :mod:`unittest` from the standard library. Tests are split into focused
fixtures (tiny purpose-built graphs) for the algorithmic units, plus one
end-to-end smoke test that drives the full showcase scenario and asserts every
required workflow surfaces.
"""

from __future__ import annotations

import contextlib
import io
import unittest

from smog_control.config import CRITICAL_PM25, TICK_HOURS
from smog_control.coordinator import CentralAICoordinator, Mission
from smog_control.dispatch import CandidateScore, FleetDispatcher
from smog_control.engine import SimulationEngine
from smog_control.enums import AQICategory, CapacityClass, NodeType, OperationalStatus
from smog_control.routing import MultiObjectiveRouter, Route
from smog_control.topology import (
    Edge,
    Node,
    RefuelingStationNode,
    SewageTreatmentPlantNode,
    TransitGraph,
)
from smog_control.trucks import MoveResult, TankerTruck


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
def line_graph() -> TransitGraph:
    """A -- B -- C with a longer direct A--C shortcut (for routing tests)."""
    g = TransitGraph()
    g.add_node(Node("A", "A", 0, 0))
    g.add_node(Node("B", "B", 1, 0))
    g.add_node(Node("C", "C", 2, 0, current_AQI_PM25=80.0))
    g.add_edge(Edge("A", "B", 3, 60), bidirectional=True)
    g.add_edge(Edge("B", "C", 3, 60), bidirectional=True)
    g.add_edge(Edge("A", "C", 5, 60), bidirectional=True)
    return g


def supply_graph() -> TransitGraph:
    """Hotspot H with an STP (S), a CNG (R) and a far junction (X)."""
    g = TransitGraph()
    g.add_node(Node("H", "Hot", 0, 0, current_AQI_PM25=400.0, radius_km=1.0))
    g.add_node(Node("X", "Far", 10, 0, current_AQI_PM25=120.0))
    g.add_node(SewageTreatmentPlantNode("S", "STP", 1, 0))
    g.add_node(RefuelingStationNode("R", "CNG", 0, 1))
    g.add_edge(Edge("H", "X", 10, 60), bidirectional=True)
    g.add_edge(Edge("H", "S", 2, 60), bidirectional=True)
    g.add_edge(Edge("X", "S", 9, 60), bidirectional=True)
    g.add_edge(Edge("H", "R", 2, 60), bidirectional=True)
    return g


# --------------------------------------------------------------------------- #
# Enums & air-quality banding                                                  #
# --------------------------------------------------------------------------- #
class TestEnums(unittest.TestCase):
    def test_aqi_classification_bands(self):
        self.assertEqual(AQICategory.classify(20), AQICategory.GOOD)
        self.assertEqual(AQICategory.classify(45), AQICategory.SATISFACTORY)
        self.assertEqual(AQICategory.classify(75), AQICategory.MODERATE)
        self.assertEqual(AQICategory.classify(100), AQICategory.POOR)
        self.assertEqual(AQICategory.classify(200), AQICategory.VERY_POOR)
        self.assertEqual(AQICategory.classify(300), AQICategory.SEVERE)

    def test_critical_band(self):
        self.assertFalse(AQICategory.classify(100).is_critical)
        self.assertTrue(AQICategory.classify(200).is_critical)

    def test_capacity_class_properties(self):
        self.assertEqual(CapacityClass.HEAVY.litres, 12000)
        self.assertGreater(
            CapacityClass.HEAVY.emission_weight, CapacityClass.MINI.emission_weight
        )
        self.assertGreater(
            CapacityClass.HEAVY.spray_rate_lpm, CapacityClass.MINI.spray_rate_lpm
        )


# --------------------------------------------------------------------------- #
# Topology                                                                     #
# --------------------------------------------------------------------------- #
class TestTopology(unittest.TestCase):
    def test_edge_speed_and_weight(self):
        e = Edge("A", "B", 3, 60, traffic_density_factor=2.0)
        self.assertAlmostEqual(e.effective_speed_kmh(), 30.0)
        self.assertAlmostEqual(e.travel_time_hours(), (3 / 60) * 2.0)
        self.assertAlmostEqual(e.base_weight(), 0.1)

    def test_factor_clamping(self):
        e = Edge("A", "B", 3, 60)
        e.set_factor(99)
        self.assertLessEqual(e.traffic_density_factor, 12.0)
        e.set_factor(-5)
        self.assertGreaterEqual(e.traffic_density_factor, 1.0)

    def test_node_zone_geometry(self):
        n = Node("H", "Hot", 0, 0, radius_km=2.0)
        self.assertTrue(n.contains_point(1.0, 1.0))     # within 2 km
        self.assertFalse(n.contains_point(5.0, 0.0))    # outside

    def test_pollution_accrual_monotonic(self):
        n = Node("H", "Hot", 0, 0, current_AQI_PM25=100.0, traffic_rate_influx=2.0)
        n.accrue_pollution()
        self.assertGreater(n.current_AQI_PM25, 100.0)

    def test_stp_dispense_capped_by_reserve(self):
        s = SewageTreatmentPlantNode("S", "STP", 0, 0, recycled_reserve_litres=500.0)
        served = s.dispense(10_000.0)
        self.assertLessEqual(served, 500.0)
        self.assertAlmostEqual(s.recycled_reserve_litres, 500.0 - served)

    def test_special_node_types(self):
        self.assertEqual(SewageTreatmentPlantNode("S", "s", 0, 0).node_type, NodeType.STP)
        self.assertEqual(RefuelingStationNode("R", "r", 0, 0).node_type, NodeType.REFUELING)


# --------------------------------------------------------------------------- #
# Routing — modified multi-objective Dijkstra                                  #
# --------------------------------------------------------------------------- #
class TestRouting(unittest.TestCase):
    def setUp(self):
        self.g = line_graph()
        self.r = MultiObjectiveRouter(self.g)

    def test_picks_cheapest_direct_path(self):
        route = self.r.shortest_path("A", "C")
        self.assertEqual(route.path, ["A", "C"])  # 5 km direct beats 6 km via B

    def test_reroutes_around_gridlock(self):
        self.g.edge("A", "C").set_factor(12.0)   # block the shortcut
        route = self.r.shortest_path("A", "C")
        self.assertEqual(route.path, ["A", "B", "C"])

    def test_emission_penalty_only_when_idling_into_critical(self):
        g = supply_graph()
        r = MultiObjectiveRouter(g)
        edge = g.edge("X", "H")           # H is critical (AQI 400)
        edge.set_factor(1.0)              # free-flow -> no penalty
        self.assertEqual(r.emission_penalty(edge, g.node("H"), CapacityClass.HEAVY), 0.0)
        edge.set_factor(4.0)              # idling -> penalty applies
        heavy = r.emission_penalty(edge, g.node("H"), CapacityClass.HEAVY)
        mini = r.emission_penalty(edge, g.node("H"), CapacityClass.MINI)
        self.assertGreater(heavy, 0.0)
        self.assertGreater(heavy, mini)  # heavier chassis penalised more

    def test_nearest_facility(self):
        g = supply_graph()
        r = MultiObjectiveRouter(g)
        route = r.nearest_facility("H", NodeType.STP)
        self.assertEqual(route.path[-1], "S")
        route_fuel = r.nearest_facility("X", NodeType.REFUELING)
        self.assertEqual(route_fuel.path[-1], "R")

    def test_unreachable_returns_none(self):
        g = TransitGraph()
        g.add_node(Node("A", "A", 0, 0))
        g.add_node(Node("Z", "Z", 9, 9))   # island
        r = MultiObjectiveRouter(g)
        self.assertIsNone(r.shortest_path("A", "Z"))


# --------------------------------------------------------------------------- #
# Trucks — kinematics & consumables                                           #
# --------------------------------------------------------------------------- #
class TestTrucks(unittest.TestCase):
    def _graph(self, dist: float) -> TransitGraph:
        g = TransitGraph()
        g.add_node(Node("A", "A", 0, 0))
        g.add_node(Node("B", "B", dist, 0))
        g.add_edge(Edge("A", "B", dist, 60), bidirectional=True)
        return g

    def test_advance_partial(self):
        g = self._graph(100)
        t = TankerTruck("T", CapacityClass.MINI, "A", water_level_liters=3000)
        t.assign_route(["A", "B"], "B", purpose="MISSION")
        res = t.advance(g, current_tick=0)
        self.assertAlmostEqual(res.moved_km, 60 * TICK_HOURS, delta=0.05)
        self.assertFalse(res.arrived)
        self.assertAlmostEqual(t.current_speed_kmh, 60.0, delta=0.01)

    def test_advance_arrival(self):
        g = self._graph(3)
        t = TankerTruck("T", CapacityClass.MINI, "A", water_level_liters=3000)
        t.assign_route(["A", "B"], "B", purpose="MISSION")
        res = t.advance(g, current_tick=0)
        self.assertTrue(res.arrived)
        self.assertEqual(t.current_node, "B")

    def test_loiter_gate_blocks_movement(self):
        g = self._graph(100)
        t = TankerTruck("T", CapacityClass.MINI, "A", water_level_liters=3000)
        t.assign_route(["A", "B"], "B", purpose="MISSION", hold_until_tick=3)
        res = t.advance(g, current_tick=1)   # before the gate
        self.assertTrue(res.loitering)
        self.assertEqual(res.moved_km, 0.0)

    def test_spray_efficiency(self):
        t = TankerTruck("T", CapacityClass.MINI, "A", water_level_liters=1000)
        full = t.spray(1.0)
        self.assertAlmostEqual(full, 1000.0)            # capped by onboard water
        t.water_level_liters = 1000
        curtain = t.spray(0.6)                            # reduced stationary mode
        self.assertAlmostEqual(curtain, 250 * 5 * 0.6)   # rate * tick * efficiency

    def test_fuel_burn_and_thresholds(self):
        t = TankerTruck("T", CapacityClass.HEAVY, "A", water_level_liters=12000, fuel_energy_pct=100)
        t._consume_fuel_for_distance(10)
        self.assertAlmostEqual(t.fuel_energy_pct, 100 - 10 * 0.55)
        t.fuel_energy_pct = 19
        self.assertTrue(t.is_low_fuel)
        t.water_level_liters = t.max_water_liters * 0.14
        self.assertTrue(t.is_low_water)


# --------------------------------------------------------------------------- #
# Dispatch — efficiency matrix, splitting, ETA sync                           #
# --------------------------------------------------------------------------- #
class TestDispatch(unittest.TestCase):
    def setUp(self):
        self.g = supply_graph()
        self.r = MultiObjectiveRouter(self.g)
        self.d = FleetDispatcher(self.r)

    def test_matrix_excludes_unavailable(self):
        fleet = [
            TankerTruck("idle", CapacityClass.MEDIUM, "X", water_level_liters=5000),
            TankerTruck("busy", CapacityClass.MEDIUM, "X", water_level_liters=5000,
                        operational_status=OperationalStatus.SPRAYING),
        ]
        matrix = self.d.efficiency_matrix(fleet, "H", v_req=4000)
        ids = {c.truck_id for c in matrix}
        self.assertIn("idle", ids)
        self.assertNotIn("busy", ids)

    def test_subfleet_covers_requirement(self):
        fleet = [
            TankerTruck("m1", CapacityClass.MINI, "X", water_level_liters=3000),
            TankerTruck("m2", CapacityClass.MINI, "X", water_level_liters=3000),
            TankerTruck("m3", CapacityClass.MINI, "X", water_level_liters=3000),
        ]
        matrix = self.d.efficiency_matrix(fleet, "H", v_req=5000)
        chosen = self.d.select_subfleet(matrix, v_req=5000)
        self.assertLessEqual(len(chosen), 3)
        self.assertGreaterEqual(sum(c.deliverable_liters for c in chosen), 5000)

    def test_eta_synchronisation_is_staggered(self):
        def cand(tid, eta, deliver):
            route = Route(path=["X", "H"], total_cost=eta / 60, travel_time_hours=eta / 60,
                          total_distance_km=eta / 6)
            return CandidateScore(tid, CapacityClass.MINI, route, eta, deliver, 90.0, 1.0, 1.0)

        slots = self.d.synchronize_etas([cand("a", 5, 1000), cand("b", 10, 1000),
                                         cand("c", 40, 1000)], current_tick=0)
        arrivals = [s.arrival_tick for s in slots]
        self.assertEqual(arrivals, sorted(arrivals))             # non-decreasing
        self.assertTrue(all(s.hold_until_tick >= 0 for s in slots))
        self.assertTrue(all(s.finish_tick > s.arrival_tick for s in slots))


# --------------------------------------------------------------------------- #
# Coordinator — prediction, supply loop, exceptions                           #
# --------------------------------------------------------------------------- #
class TestCoordinator(unittest.TestCase):
    def _coord(self, fleet):
        g = supply_graph()
        r = MultiObjectiveRouter(g)
        d = FleetDispatcher(r)
        return CentralAICoordinator(g, fleet, r, d), g

    def test_prediction_fires_on_traffic_surge(self):
        coord, g = self._coord([])
        edge = g.edge("H", "X")
        edge.factor_history.extend([1.0, 1.0, 2.0])   # +100 % over two ticks
        edge.traffic_density_factor = 2.0
        g.node("X").current_AQI_PM25 = 200.0          # in the pre-alert band
        predicted = coord.run_prediction()
        self.assertIn("X", predicted)

    def test_supply_lifecycle_routes_and_locks(self):
        truck = TankerTruck("T", CapacityClass.MINI, "X", water_level_liters=150)  # ~5 %
        coord, _ = self._coord([truck])
        coord.tick = 1
        coord.run_supply_lifecycle()
        self.assertEqual(truck.operational_status, OperationalStatus.EN_ROUTE)
        self.assertEqual(truck.route_purpose, "REPLENISH_WATER")
        self.assertTrue(truck.console_locked)
        self.assertEqual(truck.target_node, "S")

    def test_replenishment_reintegrates_and_bills(self):
        truck = TankerTruck("T", CapacityClass.MINI, "S", water_level_liters=150)
        truck.route_purpose = "REPLENISH_WATER"
        coord, _ = self._coord([truck])
        coord._begin_replenishment(truck)
        for _ in range(5):
            if truck.operational_status == OperationalStatus.IDLE:
                break
            coord._progress_replenishment(truck)
        self.assertEqual(truck.operational_status, OperationalStatus.IDLE)
        self.assertGreaterEqual(truck.water_fraction, 0.95)
        self.assertGreater(coord.total_billed_inr, 0.0)

    def test_en_route_interception_marks_stuck_and_reallocates(self):
        stuck = TankerTruck("stuck", CapacityClass.MEDIUM, "X", water_level_liters=5000)
        backup = TankerTruck("backup", CapacityClass.MEDIUM, "S", water_level_liters=5000)
        coord, g = self._coord([stuck, backup])
        coord.tick = 2
        coord.active_missions["H"] = Mission("H", v_req=5000, opened_tick=0)
        # Configure the stuck truck mid-route, far from the hotspot zone.
        stuck.operational_status = OperationalStatus.EN_ROUTE
        stuck.route_purpose = "MISSION"
        stuck.mission_id = "H"
        stuck.x, stuck.y = 10.0, 0.0    # at X, outside H's 1 km zone
        res = MoveResult(0.3, arrived=False, loitering=False, speed_kmh=3.0, current_edge=("X", "H"))
        coord._handle_stuck(stuck, res)
        self.assertEqual(stuck.operational_status, OperationalStatus.STUCK)
        self.assertTrue(stuck.console_locked)
        self.assertIsNone(stuck.mission_id)
        self.assertEqual(backup.operational_status, OperationalStatus.EN_ROUTE)  # reallocated

    def test_in_hotspot_engages_stationary_curtain(self):
        truck = TankerTruck("T", CapacityClass.HEAVY, "X", water_level_liters=12000)
        coord, g = self._coord([truck])
        coord.tick = 2
        coord.active_missions["H"] = Mission("H", v_req=5000, opened_tick=0)
        truck.operational_status = OperationalStatus.EN_ROUTE
        truck.route_purpose = "MISSION"
        truck.mission_id = "H"
        truck.x, truck.y = 0.0, 0.0     # inside H's zone
        res = MoveResult(0.2, arrived=False, loitering=False, speed_kmh=3.0, current_edge=("X", "H"))
        coord._handle_stuck(truck, res)
        self.assertEqual(truck.operational_status, OperationalStatus.SPRAYING)
        self.assertTrue(truck.stationary_misting)
        self.assertEqual(truck.current_node, "H")


# --------------------------------------------------------------------------- #
# End-to-end smoke test                                                        #
# --------------------------------------------------------------------------- #
class TestEngineSmoke(unittest.TestCase):
    def test_showcase_scenario_surfaces_all_workflows(self):
        engine = SimulationEngine(seed=7, verbose=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            engine.run_ticks(16)
        out = buf.getvalue()

        self.assertIn("[PREDICT]", out)
        self.assertIn("[DISPATCH]", out)
        self.assertIn("ETA-sync loiter", out)
        self.assertIn("EXCEPTION IN-HOTSPOT", out)
        self.assertIn("EXCEPTION EN-ROUTE", out)
        self.assertIn("[FASTPASS]", out)
        self.assertIn("[REPLENISH]", out)
        self.assertIn("[MISSION CLR]", out)
        self.assertGreaterEqual(engine.coordinator.missions_resolved, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
