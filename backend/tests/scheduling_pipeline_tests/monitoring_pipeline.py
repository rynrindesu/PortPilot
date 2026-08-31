"""Run PortPilot's monitor -> schedule generation -> rule validation pipeline.

The script reads/writes only vessel ETA observations during monitoring. It
generates and validates candidate operational plans but never applies any
allocation change to Supabase.

Usage from the repository root:
    PYTHONPATH=backend/src python backend/tests/scheduling_pipeline_tests/monitoring_pipeline.py 1 2026-08-31

Each execution appends its report to ``test_output/run_output_<n>.txt``.
"""

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from PortPilot.agent.schedule_option_generator import generate_schedule_options
from PortPilot.agent.scheduling_rules import filter_valid_options, rank_options
from PortPilot.monitoring.monitor_service import monitor_vessels

OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "test_output"


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Cannot serialise {type(value).__name__}")


def _format_json(value) -> str:
    return json.dumps(value, default=_json_default, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor arrivals and write generated, rule-validated schedule plans."
    )
    parser.add_argument(
        "run_number",
        type=int,
        help="Positive sequential test-run number, used in the output filename.",
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
    output_path = OUTPUT_DIRECTORY / f"run_output_{args.run_number}.txt"

    changes = monitor_vessels(args.arrival_date)
    eta_changes = [change for change in changes if change["event"] == "ETA_CHANGED"]
    vessel_reports = []

    for change in eta_changes:
        vessel_name = change["vessel_name"]
        imo_number = change["imo_number"]
        revised_eta = datetime.fromisoformat(change["new_eta"])

        generated_options = generate_schedule_options(
            vessel_name, imo_number, revised_eta
        )
        valid_options, invalid_options = filter_valid_options(generated_options)
        ranked_options = rank_options(valid_options)
        vessel_reports.append(
            {
                "vessel_name": vessel_name,
                "imo_number": imo_number,
                "previous_eta": change["previous_eta"],
                "revised_eta": change["new_eta"],
                "plans_proposed": len(generated_options),
                "valid_plans": len(valid_options),
                "invalid_plans": len(invalid_options),
                "ranked_plans": ranked_options[:3],
                "validated_plans": valid_options,
                "rejected_plans": invalid_options,
            }
        )

    report = {
        "title": f"PortPilot Monitoring Pipeline — Run {args.run_number}",
        "run_number": args.run_number,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "arrival_date": args.arrival_date,
        "outcome": {
            "eta_changes_detected": len(eta_changes),
            "vessels_with_plans": len(vessel_reports),
            "total_plans_proposed": sum(item["plans_proposed"] for item in vessel_reports),
            "total_valid_plans": sum(item["valid_plans"] for item in vessel_reports),
            "total_invalid_plans": sum(item["invalid_plans"] for item in vessel_reports),
        },
        "vessel_plan_summary": [
            {
                key: item[key]
                for key in (
                    "vessel_name", "imo_number", "previous_eta", "revised_eta",
                    "plans_proposed", "valid_plans", "invalid_plans",
                )
            }
            for item in vessel_reports
        ],
        "vessel_plans": vessel_reports,
    }

    rendered_report = _format_json(report)
    with output_path.open("a", encoding="utf-8") as output_file:
        output_file.write("=" * 88 + "\n")
        output_file.write(rendered_report)
        output_file.write("\n")

    print(rendered_report)
    print(f"\nAppended pipeline report to {output_path}")

    if not eta_changes:
        print("No ETA changes detected; no schedule plans require validation.")


if __name__ == "__main__":
    main()
