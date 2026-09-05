"""LLM-callable tools for PortPilot.

Four tools are exposed to the agent:
- get_vessel_schedule: read one vessel's ETA state and current allocations.
- get_ranked_options: generate, validate, and rank rescheduling plans for a revised ETA.
- reschedule_operations: apply a chosen plan's allocation changes atomically.
- flag_for_review: escalate one resource allocation for human review when no valid plan exists for a vessel.
"""

import json
from datetime import datetime

from langchain_core.tools import tool

from PortPilot.database.postgres import (
    get_vessel_schedule as read_vessel_schedule,
    get_connection,
    find_resource_conflicts,
    RESOURCE_TABLES,
)
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

    If valid_option_count is 0, invalid_reasons lists why candidates were
    rejected (e.g. FCFS priority, freeze window) - cite one when calling
    flag_for_review instead of a generic "no valid option" reason.
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
                "invalid_reasons": _summarize_invalid_reasons(invalid_options) if not valid_options else [],
                "options": ranked_options[:3],
            }
        )
    except ValueError as error:
        return _json({"found": True, "valid": False, "message": str(error)})


# Keep a short list of unique reasons why scheduling options were rejected.
# These reasons help explain why a vessel needs human review.
_MAX_INVALID_REASONS = 5

def _summarize_invalid_reasons(invalid_options):
    reasons = []
    for invalid_option in invalid_options:
        reason = invalid_option["invalid_reason"]
        if reason not in reasons:
            reasons.append(reason)
        if len(reasons) == _MAX_INVALID_REASONS:
            break
    return reasons


# --- Helpers for reschedule_operations ------------------------------------
# The functions below (_OPTION_DATETIME_FIELDS, _parse_option_datetimes,
# apply_schedule_option) are internal helpers, not tools - they have no
# @tool decorator and aren't in TOOLS. They exist only to support the
# reschedule_operations tool defined further down this file.

# Datetime fields that need converting back from JSON strings.
_OPTION_DATETIME_FIELDS = {"target_eta", "start_time", "end_time"}

# Restore datetime fields from JSON strings so they can be used in scheduling calculations.
def _parse_option_datetimes(value):
    if isinstance(value, dict):
        return {
            key: (
                datetime.fromisoformat(item)
                if key in _OPTION_DATETIME_FIELDS and isinstance(item, str)
                else _parse_option_datetimes(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_parse_option_datetimes(item) for item in value]
    return value


# Revalidate and atomically apply one complete scheduling option.

# Resources are locked before updating to prevent concurrent conflicting
# bookings. Either all changes are applied, or none are.
def apply_schedule_option(option, reason, execution_mode="autonomous"):
    # Keep the option ID so it can be included in the result.
    option_id = option.get("option_id")

    # Every applied schedule change must have a reason for the audit log.
    if not reason or not reason.strip():
        return {"success": False, "option_id": option_id, "message": "A reason is required."}
    reason = reason.strip()

    # Revalidate the chosen option against the latest schedule before applying it.
    try:
        valid_options, invalid_options = filter_valid_options([option])
    except (KeyError, TypeError, ValueError) as error:
        return {"success": False, "option_id": option_id, "message": f"Malformed option: {error}"}

    # Stop if the option has become invalid since it was originally ranked.
    if not valid_options:
        invalid_reason = invalid_options[0]["invalid_reason"] if invalid_options else "unknown reason"
        return {
            "success": False,
            "option_id": option_id,
            "message": f"Option is no longer valid: {invalid_reason}",
        }

    # Use the revalidated changes, as validation may have adjusted the option.
    changes = valid_options[0]["changes"]
    rank = valid_options[0].get("rank")

    # Every allocation this option touches, flattened and sorted by
    # (resource_type, resource_id) - the fixed order that prevents deadlock
    # between concurrent applies.
    allocations = sorted(
        (
            (resource_type, change["vessel_name"], change["imo_number"], allocation)
            for change in changes
            for resource_type, allocation in change["allocations"].items()
        ),
        key=lambda item: (item[0], item[3]["resource_id"]),
    )

    # Track vessels whose allocations are included in this option.
    # Their existing booking for the same resource type should not block
    # another allocation being reassigned within the same option.
    option_vessels_by_resource_type = {
        (change["vessel_name"], change["imo_number"], resource_type)
        for change in changes
        for resource_type in change["allocations"]
    }

    # Keep track of successfully applied changes for the final response.
    applied = []
    
    try:
        # Apply the complete option in one transaction so all changes
        # succeed together or are rolled back together.
        with get_connection() as connection:
            with connection.cursor() as cursor:
                for resource_type, vessel_name, imo_number, allocation in allocations:
                    resource_id = allocation["resource_id"]
                    table, resource_column, _id_column = RESOURCE_TABLES[resource_type]

                    # Lock the resource so another scheduling update cannot
                    # modify the same resource at the same time.
                    cursor.execute(
                        "SELECT resource_type FROM resources "
                        "WHERE resource_type = %s AND resource_id = %s FOR UPDATE",
                        (resource_type, resource_id),
                    )
                    
                    # Make sure the requested resource actually exists.
                    if cursor.fetchone() is None:
                        raise ValueError(f"{resource_type} {resource_id} is not a known active resource.")

                    # Check again for conflicts after the resource has been locked.
                    conflicts = find_resource_conflicts(
                        resource_type, resource_id,
                        allocation["start_time"], allocation["end_time"],
                        candidate_buffer_minutes=allocation["buffer_minutes"],
                        exclude_vessel_name=vessel_name, exclude_imo_number=imo_number,
                    )

                    # Ignore existing bookings that are being reassigned within this same option.
                    conflicts = [
                        conflict for conflict in conflicts
                        if (conflict["vessel_name"], conflict["imo_number"], resource_type)
                        not in option_vessels_by_resource_type
                    ]

                    # Abort the whole option if the resource is no longer available.
                    if conflicts:
                        raise ValueError(
                            f"{resource_type} {resource_id} was booked by another operation "
                            f"({conflicts[0]['vessel_name']}) after this option was validated."
                        )

                    # Read the existing allocation before replacing it.
                    # These values are also needed for the audit log.
                    cursor.execute(
                        f"SELECT {resource_column}, start_time, end_time, buffer_minutes, status "
                        f"FROM {table} WHERE vessel_name = %s AND imo_number = %s FOR UPDATE",
                        (vessel_name, imo_number),
                    )
                    row = cursor.fetchone()

                    # The option expects an existing allocation to update.
                    if row is None:
                        raise ValueError(
                            f"No existing {resource_type} allocation found for "
                            f"{vessel_name} ({imo_number})."
                        )
                    old_resource_id, old_start, old_end, old_buffer, old_status = row

                    # A pending-review allocation is controlled by the human
                    # review workflow and must not be cleared by an autonomous
                    # reschedule. This check happens after the row lock so a
                    # concurrent review flag cannot race with this update.
                    if old_status == "pending_review":
                        raise ValueError(
                            f"{vessel_name}'s {resource_type} allocation is pending human review "
                            "and cannot be changed autonomously."
                        )

                    # Replace the vessel's existing allocation with the new one.
                    cursor.execute(
                        f"UPDATE {table} SET {resource_column} = %s, start_time = %s, "
                        f"end_time = %s, buffer_minutes = %s, status = 'confirmed', updated_at = NOW() "
                        f"WHERE vessel_name = %s AND imo_number = %s",
                        (
                            resource_id, allocation["start_time"],
                            allocation["end_time"], allocation["buffer_minutes"],
                            vessel_name, imo_number,
                        ),
                    )
                    
                    # Exactly one allocation should have been updated.
                    if cursor.rowcount != 1:
                        raise ValueError(
                            f"Expected to update one {resource_type} row for "
                            f"{vessel_name} ({imo_number}), updated {cursor.rowcount}."
                        )

                    # Record what changed and why for auditing/history.
                    cursor.execute(
                        """
                        INSERT INTO schedule_changes (
                            vessel_name, imo_number, resource_type, resource_id,
                            old_start_time, old_end_time, new_start_time, new_end_time,
                            reason, decision_score, execution_mode
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            vessel_name, imo_number, resource_type, resource_id,
                            old_start, old_end, allocation["start_time"], allocation["end_time"],
                            reason, rank, execution_mode,
                        ),
                    )

                    # Add this change to the success response.
                    applied.append({
                        "vessel_name": vessel_name,
                        "imo_number": imo_number,
                        "resource_type": resource_type,
                        "old_resource_id": old_resource_id,
                        "new_resource_id": resource_id,
                        "old_start_time": old_start,
                        "new_start_time": allocation["start_time"],
                        "old_end_time": old_end,
                        "new_end_time": allocation["end_time"],
                    })
                    
    # A validation/write failure causes the transaction to roll back.
    except ValueError as error:
        return {"success": False, "option_id": option_id, "message": f"Failed to apply option: {error}"}
    
    # Return unexpected database errors in a consistent format.
    except Exception as error:
        return {"success": False, "option_id": option_id, "message": f"Unexpected error: {error}"}

    # Reaching here means the complete option was applied successfully.
    return {"success": True, "option_id": option_id, "changes_applied": applied}


@tool
def reschedule_operations(option: dict, reason: str) -> str:
    """Apply a ranked scheduling option chosen from get_ranked_options.

    Review the ranked options and their scheduling priority trade-offs before
    selecting an option. Treat the deterministic ranking as the primary
    decision guide and normally select the highest-ranked valid option.

    Use only an option returned by get_ranked_options and do not modify its
    scheduling values.

    If selecting a lower-ranked option, provide a clear reason for doing so.
    Explain the selection using the relevant scheduling priorities and
    trade-offs, rather than referring only to the option's final rank.

    The selected option is revalidated against the latest schedule before
    all changes are applied atomically.
    """
    try:
        parsed_option = _parse_option_datetimes(option)
    except ValueError as error:
        return _json({
            "success": False,
            "option_id": option.get("option_id") if isinstance(option, dict) else None,
            "message": f"Malformed option: {error}",
        })

    result = apply_schedule_option(parsed_option, reason)
    return _json(result)


# --- Helper for flag_for_review -------------------------------------------

# Mark one resource allocation as needing human review and record the reason.
# This is used when the system cannot resolve the scheduling problem automatically.
#
# The helper handles the database update, while flag_for_review() exposes it
# as an LLM-callable tool.
def flag_allocation_for_review(resource_type, vessel_name, imo_number, reason):
    # A reason is required so the escalation can be recorded in the audit log.
    if not reason or not reason.strip():
        return {"success": False, "message": "A reason is required."}
    reason = reason.strip()

    # Make sure the requested resource type is supported.
    if resource_type not in RESOURCE_TABLES:
        return {"success": False, "message": f"Unknown resource_type: {resource_type}."}

    table, resource_column, _id_column = RESOURCE_TABLES[resource_type]

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                # Read and lock the current allocation while it is being marked for review.
                cursor.execute(
                    f"SELECT {resource_column}, start_time, end_time "
                    f"FROM {table} WHERE vessel_name = %s AND imo_number = %s FOR UPDATE",
                    (vessel_name, imo_number),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(
                        f"No existing {resource_type} allocation found for "
                        f"{vessel_name} ({imo_number})."
                    )
                resource_id, start_time, end_time = row

                # Mark the allocation as requiring human review.
                cursor.execute(
                    f"UPDATE {table} SET status = 'pending_review', updated_at = NOW() "
                    f"WHERE vessel_name = %s AND imo_number = %s",
                    (vessel_name, imo_number),
                )
                if cursor.rowcount != 1:
                    raise ValueError(
                        f"Expected to update one {resource_type} row for "
                        f"{vessel_name} ({imo_number}), updated {cursor.rowcount}."
                    )

                # Record the escalation in the audit log.
                # The times stay unchanged because no rescheduling was performed.
                cursor.execute(
                    """
                    INSERT INTO schedule_changes (
                        vessel_name, imo_number, resource_type, resource_id,
                        old_start_time, old_end_time, new_start_time, new_end_time,
                        reason, decision_score, execution_mode
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        vessel_name, imo_number, resource_type, resource_id,
                        start_time, end_time, start_time, end_time,
                        reason, None, "human_review",
                    ),
                )
    except ValueError as error:
        return {"success": False, "message": f"Failed to flag for review: {error}"}
    except Exception as error:  # never let an unexpected DB error escape unstructured
        return {"success": False, "message": f"Unexpected error: {error}"}

    # Return the escalation result.
    return {
        "success": True,
        "outcome": "human_review",
        "vessel_name": vessel_name,
        "imo_number": imo_number,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "reason": reason,
    }


@tool
def flag_for_review(resource_type: str, vessel_name: str, imo_number: str, reason: str) -> str:
    """Escalate one vessel's resource allocation for human review.

    Use this when get_ranked_options() returns no valid scheduling options
    for the vessel. Mark the affected resource allocation as 'pending_review'
    and use an invalid reason returned by get_ranked_options() to explain why
    human review is required.

    This tool handles one resource_type per call.
    """
    result = flag_allocation_for_review(resource_type, vessel_name, imo_number, reason)
    return _json(result)



# -- When the model intentionally chose to not alter the schedule
#
# Prevents the outcome to be 'unable_to_resolve' eventhough the plan is valid & unchanged.
@tool
def complete_no_action(option_id: str, reason: str) -> str:
    """Complete the workflow without changing allocations.

    Use only when get_ranked_options returned a valid
    retain_current_allocation option.
    """

    if not reason or not reason.strip():
        return _json({
            "success": False,
            "message": "A reason is required.",
        })

    return _json({
        "success": True,
        "outcome": "no_action",
        "option_id": option_id,
        "reason": reason.strip(),
    })

TOOLS = [get_vessel_schedule, get_ranked_options, reschedule_operations, flag_for_review, complete_no_action]
TOOLS_BY_NAME = {tool_definition.name: tool_definition for tool_definition in TOOLS}
