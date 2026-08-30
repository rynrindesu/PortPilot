"""LLM-callable, read-only tools for PortPilot."""

import json
from datetime import datetime

from langchain_core.tools import tool

from PortPilot.database.postgres import get_vessel_schedule as read_vessel_schedule


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


TOOLS = [get_vessel_schedule]
TOOLS_BY_NAME = {tool_definition.name: tool_definition for tool_definition in TOOLS}
