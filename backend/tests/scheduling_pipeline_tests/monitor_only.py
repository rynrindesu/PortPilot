"""Run only PortPilot's vessel-monitoring step (detection + initial resource
assignment) - the part of monitoring_pipeline.py that happens before the
rescheduling pipeline (generate_schedule_options / filter_valid_options /
rank_options).

Useful for testing monitor_vessels() in isolation - e.g. checking how many
new vessels are discovered and how their initial resource assignment turns
out - without waiting through the slower ETA-change rescheduling loop.

Usage from the repository root:
    PYTHONPATH=backend/src python backend/tests/scheduling_pipeline_tests/monitor_only.py 1 2026-08-31

Each execution appends detected vessel changes to
``test_output/vessel_changes.txt``, the same file monitoring_pipeline.py
writes to.
"""

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from PortPilot.monitoring.monitor_service import monitor_vessels

OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "test_output"
VESSEL_CHANGES_PATH = OUTPUT_DIRECTORY / "vessel_changes.txt"


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Cannot serialise {type(value).__name__}")


def _format_json(value) -> str:
    return json.dumps(value, default=_json_default, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run only vessel detection and initial resource assignment."
    )
    parser.add_argument(
        "run_number",
        type=int,
        help="Positive sequential test-run number, recorded in vessel_changes.txt.",
    )
    parser.add_argument(
        "arrival_date",
        nargs="?",
        default=date.today().isoformat(),
        help="OCEANS-X arrival date in YYYY-MM-DD format (default: today).",
    )
    args = parser.parse_args()
    if args.run_number < 1:
        parser.error("run_number must be a positive integer.")

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    changes = monitor_vessels(args.arrival_date)

    eta_changes = [change for change in changes if change["event"] == "ETA_CHANGED"]
    new_vessels = [change for change in changes if change["event"] == "NEW_VESSEL_DISCOVERED"]

    vessel_change_report = {
        "run_number": args.run_number,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "arrival_date": args.arrival_date,
        "changes": changes,
    }
    rendered_vessel_changes = _format_json(vessel_change_report)
    with VESSEL_CHANGES_PATH.open("a", encoding="utf-8") as vessel_changes_file:
        vessel_changes_file.write("=" * 88 + "\n")
        vessel_changes_file.write(rendered_vessel_changes)
        vessel_changes_file.write("\n")

    print(
        f"\n{len(new_vessels)} new vessel(s) with no operational schedule - "
        f"assigned initial operations."
    )
    print(f"{len(eta_changes)} ETA change(s) detected (not processed by this script).")
    print(f"Appended {len(changes)} vessel change(s) to {VESSEL_CHANGES_PATH}")


if __name__ == "__main__":
    main()
