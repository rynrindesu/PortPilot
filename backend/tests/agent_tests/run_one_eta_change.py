"""Run one real ETA-change event through the actual compiled agent graph.

This is a LIVE test, not a mock: it makes real Groq (or Bedrock) API calls,
and if the model decides a schedule change is warranted, it WILL write to
Supabase for real via reschedule_operations or flag_for_review - the same
apply_schedule_option()/flag_allocation_for_review() paths used everywhere
else in this project. Reading (get_vessel_schedule, get_ranked_options) is
always safe; the write tools are not, and the agent decides on its own
whether to call them.

Pick the vessel and new ETA deliberately before running this - do not run
it against a vessel you are not prepared to see rescheduled for real.

Usage from the repository root:
    PYTHONPATH=backend/src python \\
        backend/tests/agent_tests/run_one_eta_change.py \\
        "VESSEL NAME" IMO_NUMBER 2026-09-06T10:00:00+00:00
"""

import argparse
import json
import sys

from PortPilot.agent.agent import SYSTEM_PROMPT, build_graph, create_model
from PortPilot.agent.graph import initial_state
from PortPilot.database.postgres import get_vessel_schedule


def _render(value):
    """json.dumps default= for datetimes and anything else str()-able."""
    return str(value)


def _print_message(message):
    role = type(message).__name__
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        for call in tool_calls:
            print(f"  [{role}] tool_call: {call['name']}({call['args']})")
        return
    content = getattr(message, "content", None)
    if content:
        text = content if isinstance(content, str) else json.dumps(content, default=_render)
        print(f"  [{role}] {text[:800]}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one real ETA-change event through the compiled agent graph."
    )
    parser.add_argument("vessel_name")
    parser.add_argument("imo_number")
    parser.add_argument("new_eta", help="ISO-8601 datetime, e.g. 2026-09-06T10:00:00+00:00")
    args = parser.parse_args()

    schedule = get_vessel_schedule(args.vessel_name, args.imo_number)
    if schedule is None:
        print(f"No vessel_state found for {args.vessel_name} ({args.imo_number}).")
        return 1

    print("Current schedule:")
    print(json.dumps(schedule, default=_render, indent=2))

    event = {
        "event": "ETA_CHANGED",
        "vessel_name": args.vessel_name,
        "imo_number": args.imo_number,
        "previous_eta": schedule["vessel"]["current_eta"].isoformat(),
        "new_eta": args.new_eta,
    }

    print(f"\nProvider: {create_model.__globals__['PROVIDER']}")
    print("Building the compiled graph...")
    compiled = build_graph(create_model(), SYSTEM_PROMPT)

    print(f"\nRunning the agent: {args.vessel_name} -> {args.new_eta}\n")
    result = compiled.invoke(initial_state(event))

    print("\n--- Full message trace ---")
    for message in result["messages"]:
        _print_message(message)

    print("\n--- Final result ---")
    print(json.dumps(result["final_result"], default=_render, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
