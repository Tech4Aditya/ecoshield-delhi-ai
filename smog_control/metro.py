"""
Delhi Metro network topology for the anti-smog tanker simulation.

Instead of a handful of abstract junctions, this module builds the operating
graph from real Delhi Metro stations (approximate coordinates) wired along their
lines, plus a set of water/charging depots where the reserve fleet rests. Water
sprinkler tankers drive the road corridors that shadow the metro lines, cleaning
PM2.5 hotspots at stations and returning to depots to replenish or stand by.

Everything downstream (router, dispatcher, coordinator, dashboard) is topology
agnostic, so swapping the 10-node core map for this ~50-node metro map needs no
changes outside this file and the engine's builder selection.
"""

from __future__ import annotations

import json
import math
import os
import re

from .config import CLEANER_FLEET_SIZE
from .enums import CapacityClass
from .topology import (
    Edge,
    Node,
    RefuelingStationNode,
    SewageTreatmentPlantNode,
    TransitGraph,
)
from .trucks import TankerTruck

# --------------------------------------------------------------------------- #
# Station coordinates (lat, lng) -- approximate real Delhi Metro locations.    #
# --------------------------------------------------------------------------- #
_STATIONS: dict[str, tuple[float, float]] = {
    # Yellow Line
    "Samaypur Badli": (28.7445, 77.1380),
    "Azadpur": (28.7076, 77.1804),
    "Vishwavidyalaya": (28.6896, 77.2095),
    "Kashmere Gate": (28.6675, 77.2281),
    "Chandni Chowk": (28.6580, 77.2300),
    "New Delhi": (28.6431, 77.2218),
    "Rajiv Chowk": (28.6328, 77.2197),
    "Central Secretariat": (28.6151, 77.2120),
    "INA": (28.5752, 77.2095),
    "AIIMS": (28.5687, 77.2070),
    "Hauz Khas": (28.5433, 77.2065),
    "Saket": (28.5205, 77.2010),
    "Qutab Minar": (28.5132, 77.1860),
    "HUDA City Centre": (28.4595, 77.0727),
    # Blue Line
    "Dwarka Sector 21": (28.5523, 77.0586),
    "Dwarka Mor": (28.6192, 77.0330),
    "Janakpuri West": (28.6293, 77.0782),
    "Rajouri Garden": (28.6469, 77.1206),
    "Kirti Nagar": (28.6552, 77.1500),
    "Karol Bagh": (28.6443, 77.1903),
    "Mandi House": (28.6256, 77.2340),
    "Yamuna Bank": (28.6230, 77.2760),
    "Akshardham": (28.6178, 77.2772),
    "Mayur Vihar Phase-1": (28.6045, 77.2895),
    "Noida Sector 18": (28.5705, 77.3260),
    "Anand Vihar": (28.6469, 77.3152),
    # Red Line
    "Rithala": (28.7212, 77.1070),
    "Netaji Subhash Place": (28.6957, 77.1520),
    "Inderlok": (28.6736, 77.1700),
    "Welcome": (28.6722, 77.2776),
    "Shahdara": (28.6735, 77.2895),
    "Dilshad Garden": (28.6757, 77.3215),
    # Violet Line
    "Lal Qila": (28.6562, 77.2410),
    "ITO": (28.6286, 77.2419),
    "Lajpat Nagar": (28.5705, 77.2435),
    "Nehru Place": (28.5494, 77.2519),
    "Kalkaji Mandir": (28.5495, 77.2588),
    "Badarpur Border": (28.4933, 77.3030),
    # Magenta Line
    "Okhla NSIC": (28.5546, 77.2740),
    "Botanical Garden": (28.5640, 77.3340),
    # Pink Line
    "Majlis Park": (28.7250, 77.1730),
    "Punjabi Bagh": (28.6680, 77.1340),
    "Mayapuri": (28.6360, 77.1290),
    "Shiv Vihar": (28.6960, 77.3300),
    # Green Line
    "Peeragarhi": (28.6759, 77.0980),
    "Mundka": (28.6822, 77.0320),
    # Airport Express
    "Shivaji Stadium": (28.6300, 77.2150),
    "Dhaula Kuan": (28.5919, 77.1610),
    "Aerocity": (28.5490, 77.1200),
    "IGI Airport T3": (28.5562, 77.0869),
}

# Lines: (name, hex colour, road base-speed km/h, ordered station list).
_LINES: list[tuple[str, str, float, list[str]]] = [
    ("Yellow", "#f2b705", 34, [
        "Samaypur Badli", "Azadpur", "Vishwavidyalaya", "Kashmere Gate",
        "Chandni Chowk", "New Delhi", "Rajiv Chowk", "Central Secretariat",
        "INA", "AIIMS", "Hauz Khas", "Saket", "Qutab Minar", "HUDA City Centre"]),
    ("Blue", "#1565c0", 36, [
        "Dwarka Sector 21", "Dwarka Mor", "Janakpuri West", "Rajouri Garden",
        "Kirti Nagar", "Karol Bagh", "Rajiv Chowk", "Mandi House", "Yamuna Bank",
        "Akshardham", "Mayur Vihar Phase-1", "Noida Sector 18"]),
    ("Blue-Branch", "#1565c0", 36, ["Yamuna Bank", "Anand Vihar"]),
    ("Red", "#e03131", 38, [
        "Rithala", "Netaji Subhash Place", "Inderlok", "Kashmere Gate",
        "Welcome", "Shahdara", "Dilshad Garden"]),
    ("Violet", "#7048e8", 32, [
        "Kashmere Gate", "Lal Qila", "ITO", "Mandi House", "Central Secretariat",
        "INA", "Lajpat Nagar", "Nehru Place", "Kalkaji Mandir", "Badarpur Border"]),
    ("Magenta", "#c2255c", 34, [
        "Janakpuri West", "Hauz Khas", "Kalkaji Mandir", "Okhla NSIC", "Botanical Garden"]),
    ("Pink", "#e64980", 36, [
        "Majlis Park", "Azadpur", "Netaji Subhash Place", "Punjabi Bagh",
        "Rajouri Garden", "Mayapuri", "INA", "Lajpat Nagar", "Mayur Vihar Phase-1",
        "Anand Vihar", "Welcome", "Shiv Vihar"]),
    ("Green", "#2f9e44", 40, ["Inderlok", "Punjabi Bagh", "Peeragarhi", "Mundka"]),
    ("Airport", "#fd7e14", 50, [
        "New Delhi", "Shivaji Stadium", "Dhaula Kuan", "Aerocity",
        "IGI Airport T3", "Dwarka Sector 21"]),
]

# Depots: (name, lat, lng, kind) where the reserve fleet rests / replenishes.
_DEPOTS: list[tuple[str, float, float, str]] = [
    ("Shastri Park Water Depot", 28.6680, 77.2540, "STP"),
    ("Najafgarh Water Depot", 28.6090, 76.9790, "STP"),
    ("Sultanpur Water Depot", 28.4990, 77.1640, "STP"),
    ("Khyber Pass Charging Hub", 28.6890, 77.2250, "REFUEL"),
    ("Sarita Vihar Charging Hub", 28.5300, 77.2900, "REFUEL"),
    ("Dwarka Charging Hub", 28.5650, 77.0500, "REFUEL"),
]

_CENTER = (28.6328, 77.2197)   # Rajiv Chowk, for "central = more polluted" bias


def slug(name: str) -> str:
    """Stable node id from a station/depot name (e.g. 'Kashmere Gate' -> 'kashmeregate')."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


# --------------------------------------------------------------------------- #
# Geometry helpers                                                            #
# --------------------------------------------------------------------------- #
def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lng) points in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dphi = math.radians(b[0] - a[0])
    dlam = math.radians(b[1] - a[1])
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _project(lat: float, lng: float) -> tuple[float, float]:
    """Equirectangular projection to a local km grid (x east, y north)."""
    lat0 = 28.6
    x = (lng - 77.0) * 111.32 * math.cos(math.radians(lat0))
    y = (lat - 28.5) * 110.57
    return round(x, 3), round(y, 3)


def _base_aqi(coord: tuple[float, float]) -> float:
    """Baseline PM2.5: central cells sit higher (denser traffic) than the fringe."""
    d = _haversine_km(coord, _CENTER)
    return 175.0 if d < 6 else (150.0 if d < 12 else 120.0)


# --------------------------------------------------------------------------- #
# Graph construction                                                          #
# --------------------------------------------------------------------------- #
def build_metro_graph() -> TransitGraph:
    """Assemble the metro-station TransitGraph (stations + depots + corridors)."""
    g = TransitGraph()

    # Map each station to the lines it serves (for the dashboard's network view).
    station_lines: dict[str, list[str]] = {}
    for line_name, _color, _speed, stops in _LINES:
        base = line_name.split("-")[0]   # treat "Blue-Branch" as "Blue"
        for s in stops:
            station_lines.setdefault(s, [])
            if base not in station_lines[s]:
                station_lines[s].append(base)

    # Stations as junction nodes carrying real geography.
    for name, coord in _STATIONS.items():
        x, y = _project(*coord)
        node = Node(
            slug(name), name, x, y,
            current_AQI_PM25=_base_aqi(coord),
            traffic_rate_influx=1.3 if _haversine_km(coord, _CENTER) < 8 else 1.0,
            radius_km=0.9, lat=coord[0], lng=coord[1],
        )
        node.line = " / ".join(station_lines.get(name, []))
        g.add_node(node)

    # Depots as STP / refuelling service nodes.
    for name, lat, lng, kind in _DEPOTS:
        x, y = _project(lat, lng)
        cls = SewageTreatmentPlantNode if kind == "STP" else RefuelingStationNode
        g.add_node(cls(
            slug(name), name, x, y,
            current_AQI_PM25=95.0, traffic_rate_influx=0.6,
            radius_km=1.0, lat=lat, lng=lng,
        ))

    # Corridor edges along each line (shared stations stitch the lines together).
    for line_name, color, speed, stops in _LINES:
        for u_name, v_name in zip(stops, stops[1:]):
            u, v = slug(u_name), slug(v_name)
            if not g.has_edge(u, v):
                dist = _haversine_km(_STATIONS[u_name], _STATIONS[v_name])
                edge = Edge(u, v, round(dist, 2), speed,
                            traffic_density_factor=1.3, line=line_name, line_color=color)
                g.add_edge(edge, bidirectional=True)
                # Tag the reverse edge with the same line for map rendering.
                g.edge(v, u).line = line_name
                g.edge(v, u).line_color = color

    # Spur each depot to its nearest station so the fleet can reach the network.
    station_coords = {slug(n): c for n, c in _STATIONS.items()}
    for name, lat, lng, _kind in _DEPOTS:
        d_id = slug(name)
        nearest, best = None, 1e9
        for s_id, c in station_coords.items():
            dist = _haversine_km((lat, lng), c)
            if dist < best:
                best, nearest = dist, s_id
        edge = Edge(d_id, nearest, round(best, 2), 40,
                    traffic_density_factor=1.2, line="Service", line_color="#9aa0a6")
        g.add_edge(edge, bidirectional=True)
        g.edge(nearest, d_id).line = "Service"
        g.edge(nearest, d_id).line_color = "#9aa0a6"

    _attach_road_geometry(g)
    return g


def _attach_road_geometry(g: TransitGraph) -> None:
    """Load cached OSRM road polylines (if present) onto each edge, both ways."""
    path = os.path.join(os.path.dirname(__file__), "edge_geometry.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as fh:
            cache = json.load(fh)
    except (OSError, ValueError):
        return
    for key, geom in cache.items():
        u, v = key.split("|")
        if g.has_edge(u, v):
            g.edge(u, v).geometry = geom
        if g.has_edge(v, u):
            g.edge(v, u).geometry = list(reversed(geom))


# --------------------------------------------------------------------------- #
# Fleet -- a reserve of resting tankers at depots plus a few forward units.    #
# --------------------------------------------------------------------------- #
def build_metro_fleet(graph: TransitGraph) -> list[TankerTruck]:
    """Create a heterogeneous fleet: most resting at depots, a few pre-positioned.

    Idle tankers parked at depots are the *reserve* ("resting") units; the
    coordinator wakes them to *clean* (spray) hotspots as AQI spikes appear, then
    returns them to the reserve once a mission clears.
    """
    H, M, Mini = CapacityClass.HEAVY, CapacityClass.MEDIUM, CapacityClass.MINI
    depots = [n.node_id for n in graph.nodes() if n.is_infrastructure]
    fleet: list[TankerTruck] = []
    n = 1

    # Two resting tankers stationed at every depot (the standby reserve).
    pattern = [H, M, Mini]
    for d in depots:
        for k in range(2):
            cls = pattern[(n - 1) % len(pattern)]
            fleet.append(TankerTruck(
                f"WT-{n:02d}", cls, d,
                water_level_liters=cls.litres,
                fuel_energy_pct=100.0 if k == 0 else 88.0,
            ))
            n += 1

    # A few forward-deployed units already on the network at busy interchanges.
    forward = [("rajivchowk", H), ("kashmeregate", M), ("ito", Mini), ("hauzkhas", M)]
    for node_id, cls in forward:
        if node_id in graph.node_ids():
            fleet.append(TankerTruck(
                f"WT-{n:02d}", cls, node_id,
                water_level_liters=cls.litres, fuel_energy_pct=92.0,
            ))
            n += 1

    # One unit starts low on charge to exercise the refuel lifecycle.
    if fleet:
        fleet[-1].fuel_energy_pct = 17.0

    # Dedicated road-cleaning fleet: these continuously patrol and wash roads,
    # binding settled dust so particles stay on the ground (not hotspot misting).
    for k in range(CLEANER_FLEET_SIZE):
        depot = depots[k % len(depots)] if depots else "rajivchowk"
        fleet.append(TankerTruck(
            f"RC-{k + 1:02d}", CapacityClass.MEDIUM, depot,
            water_level_liters=CapacityClass.MEDIUM.litres, fuel_energy_pct=100.0,
            role="CLEANER",
        ))

    for t in fleet:
        t.sync_position(graph)
    return fleet


# --------------------------------------------------------------------------- #
# Scenario -- staggered station spikes; most of the map stays calm so the      #
# reserve genuinely rests while a subset of tankers clean.                     #
# --------------------------------------------------------------------------- #
# Rotation of stations that periodically spike, so a long run stays continuously
# active (the network is large enough that a steady reserve still rests).
_SPIKE_ROTATION = [
    "Rajiv Chowk", "Hauz Khas", "Lajpat Nagar", "Peeragarhi", "Mayur Vihar Phase-1",
    "Nehru Place", "Karol Bagh", "Rajouri Garden", "Saket", "Welcome",
    "Noida Sector 18", "Dwarka Mor", "Vishwavidyalaya", "Azadpur", "Botanical Garden",
    "Janakpuri West", "Dilshad Garden", "Mundka", "Shahdara", "INA",
    "Chandni Chowk", "Qutab Minar", "Mayapuri", "Shiv Vihar",
]


def metro_scenario(horizon: int = 200) -> dict:
    """Procedurally generated, never-quiet AQI/traffic shocks across the network.

    A scripted opening (showcasing the severe spike, predictive surge and
    industrial breaches) is followed by a rolling cadence of fresh hotspots at
    rotating stations -- so the simulation runs *continuously*: tankers keep
    being woken from the reserve to clean, then cycle back to rest.
    """
    sc: dict[int, list] = {}

    def add(t, ev):
        sc.setdefault(t, []).append(ev)

    def aqi(name, v):    return ("aqi", slug(name), v)
    def influx(name, v): return ("influx", slug(name), v)
    def factor(u, v, x): return ("factor", slug(u), slug(v), x)

    # --- Scripted opening (deterministic showcase) ----------------------- #
    add(1, ("banner", "Continuous operations online: reserve tankers resting at depots."))
    add(2, ("banner", "Severe spike at Kashmere Gate interchange."))
    add(2, aqi("Kashmere Gate", 455)); add(2, influx("Kashmere Gate", 2.6))
    add(2, aqi("ITO", 360))
    add(3, ("banner", "Traffic building on the Yellow Line core."))
    add(3, factor("New Delhi", "Rajiv Chowk", 2.2)); add(3, influx("Rajiv Chowk", 2.2))
    add(3, aqi("Rajiv Chowk", 205))
    add(4, ("banner", "Industrial haze: Anand Vihar and Nehru Place breach."))
    add(4, aqi("Anand Vihar", 430)); add(4, influx("Anand Vihar", 2.5))
    add(4, aqi("Nehru Place", 345))
    add(4, factor("New Delhi", "Rajiv Chowk", 3.2)); add(4, aqi("Rajiv Chowk", 295))
    add(5, ("banner", "Peeragarhi industrial belt spikes; incidents emerging."))
    add(5, aqi("Peeragarhi", 380)); add(5, influx("Peeragarhi", 2.3))

    # --- Rolling procedural cadence from tick 6 onward ------------------- #
    ri = 0
    for t in range(6, horizon + 1):
        if t % 3 == 0:                       # a fresh hotspot every 3 ticks
            name = _SPIKE_ROTATION[ri % len(_SPIKE_ROTATION)]; ri += 1
            add(t, aqi(name, 320 + (t * 37) % 150))
            add(t, influx(name, 2.0 + (t % 3) * 0.2))
        if t % 7 == 0:                       # an occasional second front
            name = _SPIKE_ROTATION[(ri + 9) % len(_SPIKE_ROTATION)]
            add(t, aqi(name, 300 + (t * 23) % 130))
        if t % 12 == 0:
            add(t, ("banner", "New pollution wave detected across the metro network."))
    return sc
