"""Run the real production monitoring pipeline end-to-end, scoped to a small,
hand-picked set of vessels.

The script first fetches real live vessel data from OCEANS-X, then filters
the response to the selected (vessel_name, imo_number) pairs. The OCEANS-X
fetch used inside monitor_vessels() is patched to return this real filtered
data, ensuring only the selected vessels enter the monitoring pipeline.

From there, run_monitoring_cycle() runs normally: monitor_vessels() compares
live ETAs against the database, persists detected changes, and creates the
corresponding events. ETA changes are processed through the real agent graph,
while new vessels with unconfirmed allocations use the real deterministic
retry path.

This is a live integration test. LLM calls and database reads/writes are real,
so only select vessels you are prepared to modify.

Usage from the repository root (VESSEL_NAME/IMO_NUMBER given in pairs):
    PYTHONPATH=backend/src python \\
        backend/tests/agent_tests/run_monitoring_cycle_test.py \\
        2026-09-05 "AL RAHBA" 9965435 "CAPE TIGER" 9346768
"""

import argparse
import json
import sys
from unittest.mock import patch

from PortPilot.agent.agent import run_monitoring_cycle
from PortPilot.integration.oceans import get_vessels_due_to_arrive


def _render(value):
    """json.dumps default= for datetimes and anything else str()-able."""
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run run_monitoring_cycle() for real, scoped to hand-picked vessels."
    )
    parser.add_argument("date", help="Arrival date to poll OCEANS-X for, e.g. 2026-09-05")
    parser.add_argument(
        "vessel", nargs="+",
        help="VESSEL_NAME IMO_NUMBER pairs to scope the run to, e.g. "
             "\"AL RAHBA\" 9965435 \"CAPE TIGER\" 9346768",
    )
    args = parser.parse_args()

    if len(args.vessel) % 2 != 0:
        parser.error("Vessels must be given as VESSEL_NAME IMO_NUMBER pairs.")
    selected = {
        (args.vessel[i], args.vessel[i + 1])
        for i in range(0, len(args.vessel), 2)
    }

    print(f"Fetching live OCEANS-X data for {args.date}...")
    live_vessels = get_vessels_due_to_arrive(args.date)
    print(f"Received {len(live_vessels)} vessel(s) from OCEANS-X.")

    filtered = [
        vessel for vessel in live_vessels
        if (vessel["vessel_name"], vessel["imo_number"]) in selected
    ]
    found = {(vessel["vessel_name"], vessel["imo_number"]) for vessel in filtered}
    missing = selected - found
    if missing:
        print(f"WARNING: not found in today's OCEANS-X response, skipping: {sorted(missing)}")
    if not filtered:
        print("None of the selected vessels are in today's OCEANS-X response - nothing to do.")
        return 1

    print(f"\nScoping this run to {len(filtered)} vessel(s):")
    for vessel in filtered:
        print(f"  {vessel['vessel_name']} ({vessel['imo_number']}) eta={vessel['eta']}")

    print(
        "\nRunning run_monitoring_cycle() for real - this WILL write to Supabase "
        "for the selected vessels if their eta has actually changed, or if they "
        "are missing an operational assignment...\n"
    )

    with patch(
        "PortPilot.monitoring.monitor_service.get_vessels_due_to_arrive",
        return_value=filtered,
    ):
        result = run_monitoring_cycle(args.date)

    print("\n--- Result ---")
    print(json.dumps(result, default=_render, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
