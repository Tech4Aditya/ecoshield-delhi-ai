#!/usr/bin/env python3
"""
One-off: fetch real road-following geometry for every metro graph edge and cache
it to ``smog_control/edge_geometry.json``.

Uses the keyless public OSRM demo server. Run once (needs network); the cached
JSON is then embedded into the dashboards so tankers, routes and metro lines
follow actual Delhi roads instead of straight lines. Re-run to refresh.

    python3 build_geometry.py
"""

from __future__ import annotations

import json
import os
import subprocess
import time

from smog_control.metro import build_metro_graph

OSRM = "https://router.project-osrm.org/route/v1/driving/{},{};{},{}?overview=full&geometries=geojson"


def fetch(a: tuple, b: tuple):
    """Return a road-following [[lat,lng],...] polyline from a to b, or None.

    Uses curl (more reliable against the OSRM demo's throttling than urllib) with
    a few retries and exponential backoff.
    """
    url = OSRM.format(a[1], a[0], b[1], b[0])
    for attempt in range(4):
        try:
            out = subprocess.run(
                ["curl", "-s", "--max-time", "30", "-A", "ecoshield-build/1.0", url],
                capture_output=True, text=True,
            )
            d = json.loads(out.stdout)
            if d.get("code") == "Ok" and d.get("routes"):
                return [[round(c[1], 5), round(c[0], 5)]
                        for c in d["routes"][0]["geometry"]["coordinates"]]
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.0 * (attempt + 1))   # backoff: 1s, 2s, 3s
    return None


def main() -> None:
    g = build_metro_graph()
    seen, pairs = set(), []
    for e in g.edges():
        key = tuple(sorted((e.source, e.target)))
        if key not in seen:
            seen.add(key)
            pairs.append(key)
    print(f"{len(pairs)} undirected edges to fetch from OSRM...")

    cache = {}
    for i, (u, v) in enumerate(pairs, 1):
        nu, nv = g.node(u), g.node(v)
        geom = None
        try:
            geom = fetch((nu.lat, nu.lng), (nv.lat, nv.lng))
        except Exception as ex:  # noqa: BLE001 - tolerate any per-edge failure
            print(f"  ! {u}->{v} failed: {ex}")
        if not geom:
            geom = [[nu.lat, nu.lng], [nv.lat, nv.lng]]   # straight-line fallback
        cache[f"{u}|{v}"] = geom
        print(f"  {i}/{len(pairs)} {u}->{v}: {len(geom)} pts")
        time.sleep(0.6)

    out = os.path.join("smog_control", "edge_geometry.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, separators=(",", ":"))
    pts = sum(len(v) for v in cache.values())
    print(f"Wrote {out}: {len(cache)} edges, {pts} points")


if __name__ == "__main__":
    main()
