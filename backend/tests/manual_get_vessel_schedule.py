"""Print a live get_vessel_schedule result from the configured Supabase database.

Usage from the backend directory:
    PYTHONPATH=src ../.venv/bin/python tests/manual_get_vessel_schedule.py

Optionally provide a different valid vessel identity:
    PYTHONPATH=src ../.venv/bin/python tests/manual_get_vessel_schedule.py \
        "VESSEL NAME" "IMO_NUMBER"
"""

import json
import sys

from PortPilot.agent.tools import get_vessel_schedule


DEFAULT_VESSEL_NAME = "ALEGRIA"
DEFAULT_IMO_NUMBER = "9169392"
INVALID_VESSEL_NAME = "UNKNOWN VESSEL"
INVALID_IMO_NUMBER = "0000000"


def print_schedule_result(label: str, vessel_name: str, imo_number: str) -> None:
    """Run a read-only tool lookup and label its JSON response in the terminal."""
    print(f"\n--- {label} ---")
    print(f"Vessel: {vessel_name} / IMO: {imo_number}")
    result = get_vessel_schedule.invoke(
        {"vessel_name": vessel_name, "imo_number": imo_number}
    )
    print(json.dumps(json.loads(result), indent=2))


def main() -> None:
    vessel_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VESSEL_NAME
    imo_number = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_IMO_NUMBER

    print_schedule_result("VALID VESSEL LOOKUP", vessel_name, imo_number)
    print_schedule_result(
        "EXPECTED NOT-FOUND RESULT",
        INVALID_VESSEL_NAME,
        INVALID_IMO_NUMBER,
    )


if __name__ == "__main__":
    main()
