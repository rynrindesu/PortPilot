"""Read-only preview of which scheduling strategies get_ranked_options would
actually offer for a vessel/new-eta pair, without running the agent or
writing anything to Supabase.

generate_schedule_options(), filter_valid_options(), and rank_options() are
all pure reads/computation (scheduling_rules.py's own docstring: "does not
use an LLM or modify the database") - this just calls that same pipeline
directly and prints each valid option's strategy, rank, and which vessels
it touches. Useful for checking in advance whether a candidate vessel/eta
would actually produce a specific strategy (e.g. reallocate_one_vessel)
before committing to a real run_monitoring_cycle_test.py call.

Usage from the repository root:
    PYTHONPATH=backend/src python \\
        backend/tests/agent_tests/preview_strategies.py \\
        "VESSEL NAME" IMO_NUMBER 2026-09-06T10:00:00+00:00
"""

import argparse
import sys
from datetime import datetime

from PortPilot.agent.schedule_option_generator import generate_schedule_options
from PortPilot.agent.scheduling_rules import filter_valid_options, rank_options


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview which scheduling strategies a vessel/new-eta pair would produce."
    )
    parser.add_argument("vessel_name")
    parser.add_argument("imo_number")
    parser.add_argument("new_eta", help="ISO-8601 datetime, e.g. 2026-09-06T10:00:00+00:00")
    args = parser.parse_args()

    new_eta = datetime.fromisoformat(args.new_eta)

    candidates = generate_schedule_options(args.vessel_name, args.imo_number, new_eta)
    print(f"generate_schedule_options: {len(candidates)} candidate(s)")

    valid_options, invalid_options = filter_valid_options(candidates)
    print(f"filter_valid_options: {len(valid_options)} valid, {len(invalid_options)} invalid")

    if invalid_options:
        print("\nInvalid candidates (rejected before ranking):")
        for option in invalid_options:
            print(f"  {option['option_id']} ({option['strategy']}): {option.get('invalid_reason')}")

    if not valid_options:
        print("\nNo valid options - nothing to rank.")
        return 1

    ranked = rank_options(valid_options)

    print("\nRanked valid options:")
    for option in ranked:
        vessels_touched = [
            f"{change['vessel_name']} ({change['imo_number']})"
            for change in option["changes"]
        ]
        print(
            f"  rank {option['rank']}: {option['option_id']} "
            f"strategy={option['strategy']} vessels={vessels_touched}"
        )

    strategies_present = sorted({option["strategy"] for option in ranked})
    print(f"\nStrategies present in this result: {strategies_present}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
