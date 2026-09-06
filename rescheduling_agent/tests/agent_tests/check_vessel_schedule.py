"""Read-only check: print get_vessel_schedule() for one or more vessels, to
verify what a real write actually persisted.

Usage from the repository root:
    PYTHONPATH=backend/src python \
        backend/tests/agent_tests/check_vessel_schedule.py \
        "SEA FLYTE" 8623248 "QUEEN STAR 8" 9797125 "UNITY OF MAJESTIC" 1035284
"""

import json
import sys

from PortPilot.database.postgres import get_vessel_schedule


def render(value):
    return str(value)


def main() -> None:
    args = sys.argv[1:]
    if len(args) % 2 != 0:
        print("Vessels must be given as VESSEL_NAME IMO_NUMBER pairs.")
        sys.exit(1)

    for i in range(0, len(args), 2):
        vessel_name, imo_number = args[i], args[i + 1]
        schedule = get_vessel_schedule(vessel_name, imo_number)
        print(f"=== {vessel_name} ({imo_number}) ===")
        print(json.dumps(schedule, default=render, indent=2, ensure_ascii=False))
        print()


if __name__ == "__main__":
    main()