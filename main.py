"""
Project launcher for the Hybrid Grid Digital Twin Simulation.

Default behavior:
- Runs the same safe demo flow as example_simulation.py

Optional behavior:
- Run full IEEE13 feeder simulation with --full-ieee13
"""

import argparse
import sys

from example_simulation import main as run_demo
from example_simulation import example_ieee13_simulation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Hybrid Grid Digital Twin Simulation project"
    )
    parser.add_argument(
        "--full-ieee13",
        action="store_true",
        help="Run the full IEEE13 OpenDSS simulation instead of the lightweight demo",
    )
    return parser.parse_args()


def run() -> int:
    args = parse_args()

    if args.full_ieee13:
        example_ieee13_simulation()
    else:
        run_demo()

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
