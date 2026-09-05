"""Run PortPilot's monitor -> schedule generation -> rule validation pipeline.

For ETA changes, the script only generates, validates, and ranks candidate operational plans; it does not apply any changes to Supabase.

For new vessels with an unconfirmed initial resource assignment, the script does update Supabase. 
It retries scheduling through the same generate → filter → rank pipeline, 
then either applies the highest-ranked valid option and confirms the allocation, 
or escalates it to pending_review if no valid option is found.

Usage from the repository root:
    PYTHONPATH=backend/src python backend/tests/scheduling_pipeline_tests/monitoring_pipeline.py 1 2026-08-31

Each execution appends detected vessel changes (new vessels, ETA changes) to
``test_output/vessel_changes.txt``, appends the rescheduling report
(generated/validated/ranked plans) to ``test_output/run_output_<n>.txt``, and
appends unconfirmed-vessel retry results to
``test_output/unconfirmed_retries.txt``.
"""

import argparse
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

from PortPilot.agent.schedule_option_generator import generate_schedule_options
from PortPilot.agent.scheduling_rules import filter_valid_options, rank_options
from PortPilot.monitoring.monitor_service import monitor_vessels, retry_unconfirmed_operations

OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "test_output"
VESSEL_CHANGES_PATH = OUTPUT_DIRECTORY / "vessel_changes.txt"
RETRY_RESULTS_PATH = OUTPUT_DIRECTORY / "unconfirmed_retries.txt"


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
    print(f"Appended {len(changes)} vessel change(s) to {VESSEL_CHANGES_PATH}")

    eta_changes = [change for change in changes if change["event"] == "ETA_CHANGED"]
    new_vessels = [change for change in changes if change["event"] == "NEW_VESSEL_DISCOVERED"]
    vessel_reports = []

    print(
        f"\n{len(new_vessels)} new vessel(s) with no operational schedule - "
        f"assigned initial operations."
    )
    print(f"{len(eta_changes)} ETA change(s) to validate and rank.")

    for index, change in enumerate(eta_changes, start=1):
        vessel_name = change["vessel_name"]
        imo_number = change["imo_number"]
        revised_eta = datetime.fromisoformat(change["new_eta"])

        print(f"\n[{index}/{len(eta_changes)}] {vessel_name} ({imo_number}) -> {revised_eta.isoformat()}")

        # One bad vessel (missing data, an unexpected error from any stage)
        # must not crash the whole batch and lose every other vessel's
        # already-computed results 
        try:
            started_at = time.perf_counter()
            generated_options = generate_schedule_options(
                vessel_name, imo_number, revised_eta
            )

            print(
                f"  generate_schedule_options: {len(generated_options)} candidate(s) "
                f"in {time.perf_counter() - started_at:.3f}s"
            )

            started_at = time.perf_counter()
            valid_options, invalid_options = filter_valid_options(generated_options)
            print(
                f"  filter_valid_options: {len(valid_options)} valid, {len(invalid_options)} invalid "
                f"in {time.perf_counter() - started_at:.3f}s"
            )

            started_at = time.perf_counter()
            ranked_options = rank_options(valid_options)
            print(
                f"  rank_options: ranked {len(ranked_options)} option(s) "
                f"in {time.perf_counter() - started_at:.3f}s"
            )
        except Exception as error:
            print(f"  Skipping {vessel_name} ({imo_number}) due to error: {error}")
            continue

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

    # Retry unconfirmed new vessels after ETA-change rescheduling.
    # Apply the best valid option, or escalate to pending_review if none exists.
    unconfirmed_vessels = [
        change for change in new_vessels
        if any(info["status"] == "unconfirmed" for info in change["assigned"].values())
    ]
    if unconfirmed_vessels:
        print(
            f"\n{len(unconfirmed_vessels)} new vessel(s) have an unconfirmed resource - "
            f"retrying via generate_schedule_options/filter_valid_options/rank_options."
        )

    retry_reports = []

    for index, change in enumerate(unconfirmed_vessels, start=1):
        vessel_name = change["vessel_name"]
        imo_number = change["imo_number"]
        before = {
            resource_type: info for resource_type, info in change["assigned"].items()
            if info["status"] == "unconfirmed"
        }

        print(f"\n[{index}/{len(unconfirmed_vessels)}] Retrying {vessel_name} ({imo_number})")
        print(f"  before: {before}")

        # One bad vessel must not crash the run and lose the ETA-change
        # results already computed above, or the retry results for every
        # other vessel already processed in this loop.
        started_at = time.perf_counter()
        try:
            retry_result = retry_unconfirmed_operations(vessel_name, imo_number)
            elapsed = time.perf_counter() - started_at

            after = {}
            if retry_result["outcome"] == "resources_allocated":
                after = {
                    item["resource_type"]: {"resource_id": item["new_resource_id"], "status": "confirmed"}
                    for item in retry_result["applied"]["changes_applied"]
                    if item["vessel_name"] == vessel_name and item["imo_number"] == imo_number
                }
                print(f"  after:  {after}")
            elif retry_result["outcome"] == "pending_review":
                after = {
                    result["resource_type"]: {"resource_id": result.get("resource_id"), "status": "pending_review"}
                    for result in retry_result["escalated"] if result.get("success")
                }
                print(f"  after:  {after}  (escalated for human review)")
            else:
                print(f"  outcome: {retry_result['outcome']}")
                if retry_result.get("applied"):
                    print(f"    {retry_result['applied']}")

            print(f"  retry_unconfirmed_operations: {elapsed:.3f}s")

            retry_reports.append({
                "vessel_name": vessel_name,
                "imo_number": imo_number,
                "before": before,
                "outcome": retry_result["outcome"],
                "after": after,
                "elapsed_seconds": elapsed,
            })
        except Exception as error:
            elapsed = time.perf_counter() - started_at
            print(f"  Skipping {vessel_name} ({imo_number}) due to error: {error}")
            retry_reports.append({
                "vessel_name": vessel_name,
                "imo_number": imo_number,
                "before": before,
                "outcome": "error",
                "error": str(error),
                "elapsed_seconds": elapsed,
            })
            continue

    retry_report = {
        "run_number": args.run_number,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "arrival_date": args.arrival_date,
        "outcome": {
            "unconfirmed_vessels_retried": len(retry_reports),
            "retry_resources_allocated": sum(1 for item in retry_reports if item["outcome"] == "resources_allocated"),
            "retry_pending_review": sum(1 for item in retry_reports if item["outcome"] == "pending_review"),
            "retry_errors": sum(1 for item in retry_reports if item["outcome"] == "error"),
        },
        "unconfirmed_retries": retry_reports,
    }
    rendered_retry_report = _format_json(retry_report)
    with RETRY_RESULTS_PATH.open("a", encoding="utf-8") as retry_results_file:
        retry_results_file.write("=" * 88 + "\n")
        retry_results_file.write(rendered_retry_report)
        retry_results_file.write("\n")
    print(f"\nAppended {len(retry_reports)} unconfirmed retry result(s) to {RETRY_RESULTS_PATH}")

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
