"""
Project launcher for the Hybrid Grid Digital Twin Simulation.

Default behavior:
- Runs the same safe demo flow as example_simulation.py

Optional behavior:
- Run full IEEE13 feeder simulation with --full-ieee13
"""

import argparse
import shutil
import sys
from pathlib import Path

from example_simulation import main as run_demo
from example_simulation import example_ieee13_simulation


def _relocate_main_outputs(base_dir: Path) -> None:
    """Move outputs generated through main.py into an isolated folder."""
    main_output_dir = base_dir / "results" / "main_ieee"
    main_output_dir.mkdir(parents=True, exist_ok=True)

    # Demo output created by example_with_realistic_profiles()
    demo_profile = base_dir / "results" / "load_profiles.csv"
    if demo_profile.exists():
        demo_dst = main_output_dir / "load_profiles.csv"
        if demo_dst.exists():
            demo_dst.unlink()
        shutil.move(str(demo_profile), str(demo_dst))

    # Full IEEE13 output folder created by example_ieee13_simulation()
    ieee13_src = base_dir / "results" / "ieee13_example"
    if ieee13_src.exists():
        for src_file in ieee13_src.iterdir():
            if src_file.is_file():
                dst_file = main_output_dir / src_file.name
                if dst_file.exists():
                    dst_file.unlink()
                shutil.move(str(src_file), str(dst_file))

        # Remove source directory if empty after moving files.
        try:
            ieee13_src.rmdir()
        except OSError:
            pass


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
    project_root = Path(__file__).resolve().parent

    if args.full_ieee13:
        example_ieee13_simulation()
        _relocate_main_outputs(project_root)
    else:
        run_demo()
        _relocate_main_outputs(project_root)

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
