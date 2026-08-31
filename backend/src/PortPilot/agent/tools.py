"""LLM-callable, read-only tools for PortPilot."""

import json
from datetime import datetime

from langchain_core.tools import tool

from PortPilot.database.postgres import get_vessel_schedule as read_vessel_schedule
from PortPilot.agent.schedule_option_generator import generate_schedule_options
from PortPilot.agent.scheduling_rules import filter_valid_options, rank_options


def _json(value) -> str:
    """Serialize database timestamps into model-readable ISO-8601 JSON."""
    return json.dumps(
        value,
        default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item),
    )


@tool
def get_vessel_schedule(vessel_name: str, imo_number: str) -> str:
    """Get one vessel's ETA state and current berth, pilot, and tug allocations.

    Use this before evaluating an ETA change or explaining a schedule decision.
    The vessel is identified only by vessel_name and imo_number. This tool reads
    data and never changes any allocation.
    """
    try:
        schedule = read_vessel_schedule(vessel_name, imo_number)
    except ValueError as error:
        return _json({"found": True, "valid": False, "message": str(error)})

    if schedule is None:
        return _json(
            {
                "found": False,
                "message": "No active vessel state found for this vessel name and IMO number.",
            }
        )

    return _json(
        {
            "found": True,
            "valid": True,
            "vessel": schedule["vessel"],
            "allocations": schedule["allocations"],
        }
    )


@tool
def get_ranked_options(vessel_name: str, imo_number: str, new_eta: datetime) -> str:
    """Generate, validate, and rank schedule plans for a revised vessel ETA.

    Each returned option contains one berth, pilot, and tug allocation for
    every affected vessel. The deterministic generator creates candidates,
    the scheduling rules remove infeasible candidates, and the remaining
    options are ranked according to the configured priority order. This tool
    only proposes plans; it never changes the database.
    """
    try:
        schedule = read_vessel_schedule(vessel_name, imo_number)
        if schedule is None:
            return _json(
                {
                    "found": False,
                    "valid": False,
                    "message": "No active vessel state found for this vessel name and IMO number.",
                }
            )

        generated_options = generate_schedule_options(vessel_name, imo_number, new_eta)
        valid_options, invalid_options = filter_valid_options(generated_options)
        ranked_options = rank_options(valid_options)

        return _json(
            {
                "found": True,
                "valid": True,
                "vessel": schedule["vessel"],
                "previous_allocation": schedule["allocations"],
                "generated_option_count": len(generated_options),
                "valid_option_count": len(valid_options),
                "invalid_option_count": len(invalid_options),
                "options": ranked_options[:3],
            }
        )
    except ValueError as error:
        return _json({"found": True, "valid": False, "message": str(error)})


TOOLS = [get_vessel_schedule, get_ranked_options]
TOOLS_BY_NAME = {tool_definition.name: tool_definition for tool_definition in TOOLS}
