"""Initialise PortPilot's live and simulated operational database state.

This is a one-time setup script. It fetches OCEANS-X arrivals for an arrival
date, stores first observations in ``vessel_state``, then seeds pilot, tug,
and berth allocations plus the ``resources`` master list in Supabase.

Usage from the repository root:
    PYTHONPATH=backend/src python backend/tests/scheduling_pipeline_tests/initialize_database.py 2026-08-31
"""

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from data.generate_seed_operations import generate_operations
from PortPilot.database.postgres import get_all_vessel_states
from PortPilot.monitoring.monitor_service import monitor_vessels


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch first vessel observations and seed PortPilot operations."
    )
    parser.add_argument(
        "arrival_date",
        nargs="?",
        default=date.today().isoformat(),
        help="OCEANS-X arrival date in YYYY-MM-DD format (default: today).",
    )
    parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Seed schedules for vessels not yet scheduled when vessel_state already has rows.",
    )
    args = parser.parse_args()

    existing_vessels = get_all_vessel_states()
    if existing_vessels and not args.allow_existing:
        raise SystemExit(
            f"vessel_state already contains {len(existing_vessels)} vessel(s). "
            "This setup script is intended for the first import. Use "
            "--allow-existing only to seed schedules missing from existing data."
        )

    print(f"Fetching initial OCEANS-X observations for {args.arrival_date}...")
    changes = monitor_vessels(args.arrival_date)
    if changes:
        # This can only happen when --allow-existing was used. A first import
        # should create observations, not report ETA changes.
        print(f"Monitoring also detected {len(changes)} pre-existing ETA change(s).")

    vessels = get_all_vessel_states()
    if not vessels:
        raise SystemExit("OCEANS-X returned no vessels; no operational schedules were seeded.")

    print(f"Seeding operational schedules and resource master list for {len(vessels)} vessel(s)...")
    generated = generate_operations()
    counts = Counter({resource_type: len(rows) for resource_type, rows in generated.items()})

    print("Initialisation complete.")
    print(f"  vessel_state: {len(vessels)} row(s)")
    print(f"  pilot assignments created: {counts['pilot']}")
    print(f"  tug assignments created: {counts['tug']}")
    print(f"  berth allocations created: {counts['berth']}")
    print("  resource master list: seeded/updated by generate_operations()")


if __name__ == "__main__":
    main()
