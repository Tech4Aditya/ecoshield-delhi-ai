#!/usr/bin/env python3
"""
Entry point for the Agentic AI Pollution-Control System simulation.

Usage
-----
    python3 main.py                 # default 12-tick scenario, seed 7
    python3 main.py --ticks 16      # run more steps
    python3 main.py --seed 42       # different background-noise stream
    python3 main.py --quiet         # suppress the per-tick dashboard

The default run is scripted to deterministically exercise every required
workflow: predictive spike pre-emption, multi-truck workload splitting with
staggered ETAs, both "stuck in traffic" exception branches (in-hotspot
stationary misting and en-route interception + reallocation), and the autonomous
closed-loop water/fuel replenishment lifecycle.
"""

from __future__ import annotations

import argparse

from smog_control import SimulationEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delhi agentic anti-smog tanker-fleet simulation."
    )
    parser.add_argument("--ticks", type=int, default=16, help="number of simulation ticks")
    parser.add_argument("--seed", type=int, default=7, help="PRNG seed for background dynamics")
    parser.add_argument("--quiet", action="store_true", help="suppress the per-tick dashboard")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    engine = SimulationEngine(seed=args.seed, verbose=not args.quiet)
    engine.run_ticks(args.ticks)


if __name__ == "__main__":
    main()
