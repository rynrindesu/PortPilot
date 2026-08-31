"""Run filter_valid_options() against the raw candidates saved by
save_generated_options.py, and write a report to run_output_<n>.txt -
replacing whatever was there before, not appending.

Unlike replay_filter_valid_options.py (which reconstructs a prior run's
candidates from its OWN already-filtered validated_plans + rejected_plans),
this reads the raw, unfiltered generate_schedule_options() output straight
from generate_schedule_options_output.txt - so this is testing
filter_valid_options() against freshly (re-)generated candidates, not a
replay of an old filtering decision.

Usage from the repository root:
    PYTHONPATH=backend/src python backend/tests/scheduling_pipeline_tests/filter_generated_options_snapshot.py 2

Writes (overwrites) run_output_2.txt with the result.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from PortPilot.agent.scheduling_rules import filter_valid_options

OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "test_output"
SNAPSHOT_PATH = OUTPUT_DIRECTORY / "generate_schedule_options_output.txt"
REPORT_SEPARATOR = "=" * 88


def _parse_datetimes(value):
    """Undo json.dumps(default=...)'s value.isoformat() serialisation."""
    if isinstance(value, dict):
        return {key: _parse_datetimes(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_parse_datetimes(item) for item in value]
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def _load_report(path):
    text = path.read_text()
    blocks = [block.strip() for block in text.split(REPORT_SEPARATOR) if block.strip()]
    return _parse_datetimes(json.loads(blocks[-1]))


def _load_snapshot(path):
    return _parse_datetimes(json.loads(path.read_text()))


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Cannot serialise {type(value).__name__}")


def _format_json(value):
    return json.dumps(value, default=_json_default, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Run filter_valid_options() against a saved generate_schedule_options() snapshot."
    )
    parser.add_argument("target_run_number", type=int, help="run_output_<n>.txt to write the result to (overwritten).")
    args = parser.parse_args()

    target_path = OUTPUT_DIRECTORY / f"run_output_{args.target_run_number}.txt"

    snapshot = _load_snapshot(SNAPSHOT_PATH)

    # Carry the arrival_date over from the run the snapshot's vessels/ETAs
    # were taken from, for consistency with monitoring_pipeline.py's reports.
    arrival_date = None
    source_run_path = OUTPUT_DIRECTORY / f"run_output_{snapshot['source_run_number']}.txt"
    if source_run_path.exists():
        arrival_date = _load_report(source_run_path).get("arrival_date")

    vessel_reports = []
    for vessel in snapshot["vessel_options"]:
        generated_options = vessel["generated_options"]

        valid_options, invalid_options = filter_valid_options(generated_options)
        vessel_reports.append(
            {
                "vessel_name": vessel["vessel_name"],
                "imo_number": vessel["imo_number"],
                "revised_eta": vessel["revised_eta"],
                "plans_proposed": len(generated_options),
                "valid_plans": len(valid_options),
                "invalid_plans": len(invalid_options),
                "validated_plans": valid_options,
                "rejected_plans": invalid_options,
            }
        )

    report = {
        "title": f"PortPilot Monitoring Pipeline — Run {args.target_run_number} "
                 f"(filtered from generate_schedule_options_output.txt, "
                 f"itself sourced from run {snapshot['source_run_number']})",
        "run_number": args.target_run_number,
        "generated_options_snapshot_generated_at": snapshot["generated_at"],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "arrival_date": arrival_date,
        "outcome": {
            "eta_changes_detected": len(vessel_reports),
            "vessels_with_plans": len(vessel_reports),
            "total_plans_proposed": sum(item["plans_proposed"] for item in vessel_reports),
            "total_valid_plans": sum(item["valid_plans"] for item in vessel_reports),
            "total_invalid_plans": sum(item["invalid_plans"] for item in vessel_reports),
        },
        "vessel_plan_summary": [
            {
                key: item[key]
                for key in (
                    "vessel_name", "imo_number", "revised_eta",
                    "plans_proposed", "valid_plans", "invalid_plans",
                )
            }
            for item in vessel_reports
        ],
        "vessel_plans": vessel_reports,
    }

    rendered_report = _format_json(report)
    target_path.write_text(rendered_report + "\n", encoding="utf-8")

    print(rendered_report)
    print(f"\nWrote report to {target_path} (replaced, not appended)")


if __name__ == "__main__":
    main()
