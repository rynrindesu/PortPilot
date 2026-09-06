import random
from PortPilot.integration.oceans import get_vessels_due_to_arrive
from datetime import datetime, timedelta, timezone

from PortPilot.database.postgres import (
    get_vessel_state,
    get_vessel_schedule,
    record_eta_change,
    refresh_vessel_observation,
    save_new_vessel_observation,
    get_connection,
    get_active_resources,
    get_allocations_in_window,
    get_allocation_keys_by_type,
    index_allocations_by_resource,
    RESOURCE_TABLES,
)
from PortPilot.agent.schedule_option_generator import generate_schedule_options
from PortPilot.agent.scheduling_rules import filter_valid_options, rank_options
from PortPilot.agent.tools import apply_schedule_option, flag_allocation_for_review


# Pick a conflict-free resource if available.
# Otherwise create an unconfirmed assignment for later rescheduling.
def pick_available_resource(candidates, is_available):
    shuffled = list(candidates)
    random.shuffle(shuffled)
    for resource_id in shuffled:
        if is_available(resource_id):
            return resource_id, "confirmed"
    return random.choice(candidates), "unconfirmed"


def normalize_eta(value):
    if isinstance(value, datetime):
        eta = value
    else:
        eta = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if eta.tzinfo is None:
        eta = eta.replace(tzinfo=timezone.utc)

    return eta.astimezone(timezone.utc)

# New vessels do not have seeded operations, so their initial
# pilot, tug, and berth durations use the same ranges as seed data.
PILOT_DURATION_RANGE_HOURS = (0.5, 2)
TUG_DURATION_RANGE_MINUTES = (30, 60)
BERTH_DURATION_RANGE_HOURS = (4, 12)
DEFAULT_BUFFER_MINUTES = 15

# Time range used to bulk-fetch possible conflicts for a vessel.
CONFLICT_WINDOW_LOOKBACK = timedelta(hours=2)
CONFLICT_WINDOW_LOOKAHEAD = timedelta(hours=13)


# Build the initial operation window for a resource based on the vessel ETA.
def _build_initial_window(resource_type, eta):
    if resource_type == "pilot":
        duration = timedelta(hours=random.uniform(*PILOT_DURATION_RANGE_HOURS))
        return eta - duration, eta
    if resource_type == "tug":
        duration = timedelta(minutes=random.uniform(*TUG_DURATION_RANGE_MINUTES))
        return eta, eta + duration
    duration = timedelta(hours=random.uniform(*BERTH_DURATION_RANGE_HOURS))
    return eta, eta + duration


# Check whether a candidate resource overlaps an existing booking.
def _has_conflict(allocations_by_resource, resource_type, resource_id, start_time, end_time):
    occupied_end = end_time + timedelta(minutes=DEFAULT_BUFFER_MINUTES)
    for booking in allocations_by_resource.get((resource_type, resource_id), []):
        booking_occupied_end = booking["end_time"] + timedelta(minutes=booking["buffer_minutes"])
        if start_time < booking_occupied_end and booking["start_time"] < occupied_end:
            return True
    return False


# Assign any missing berth, pilot, or tug operations for a vessel.
# Existing allocation keys are pre-fetched once per monitoring poll.
def assign_initial_operations(vessel_name, imo_number, eta, is_new_vessel, existing_allocation_keys):
    if is_new_vessel:
        missing_resource_types = list(RESOURCE_TABLES)
    else:
        vessel_key = (vessel_name, imo_number)
        missing_resource_types = [
            resource_type for resource_type in RESOURCE_TABLES
            if vessel_key not in existing_allocation_keys[resource_type]
        ]
    if not missing_resource_types:
        return {}

    resources = get_active_resources()
    assigned = {}

    # Fetch and index potentially conflicting bookings once for this vessel.
    window_start = eta - CONFLICT_WINDOW_LOOKBACK
    window_end = eta + CONFLICT_WINDOW_LOOKAHEAD
    allocations_by_resource = index_allocations_by_resource(
        get_allocations_in_window(window_start, window_end)
    )

    # For each missing resource, build its time window
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for resource_type in missing_resource_types:
                table, resource_column, _id_column = RESOURCE_TABLES[resource_type]
                candidates = resources.get(resource_type, [])
                if not candidates:
                    raise ValueError(f"No active {resource_type} resources exist to assign.")

                start_time, end_time = _build_initial_window(resource_type, eta)

                # Try to find a resource for that window
                resource_id, status = pick_available_resource(
                    candidates,
                    lambda candidate_id: not _has_conflict(
                        allocations_by_resource, resource_type, candidate_id, start_time, end_time,
                    ),
                )

                cursor.execute(
                    f"""
                    INSERT INTO {table} (
                        vessel_name, imo_number, {resource_column},
                        start_time, end_time, buffer_minutes, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (vessel_name, imo_number) DO NOTHING
                    """,
                    (
                        vessel_name, imo_number, resource_id,
                        start_time, end_time, DEFAULT_BUFFER_MINUTES, status,
                    ),
                )
                
                # Only record the assignment if this process inserted it.
                if cursor.rowcount == 1:
                    assigned[resource_type] = {"resource_id": resource_id, "status": status}

    return assigned


def monitor_vessels(
    date,
    not_before=None,
    current_vessels=None,
    assign_operations=True,
):
    print("Fetching OCEANS-X data...")
    if current_vessels is None:
        current_vessels = get_vessels_due_to_arrive(date)
    else:
        current_vessels = list(current_vessels)

    if not_before is not None:
        cutoff = normalize_eta(not_before)
        original_count = len(current_vessels)
        current_vessels = [
            vessel
            for vessel in current_vessels
            if normalize_eta(vessel["eta"]) >= cutoff
        ]
        skipped_count = original_count - len(current_vessels)
        if skipped_count:
            print(f"Skipped {skipped_count} vessel(s) whose ETA has already passed.")

    current_vessels.sort(key=lambda vessel: normalize_eta(vessel["eta"]))

    print(f"Received {len(current_vessels)} vessels.")

    # Batch-fetch which vessels already have an allocation of each type
    # once for the whole poll, instead of querying it once per vessel.
    existing_allocation_keys = get_allocation_keys_by_type()

    changes = []

    for vessel in current_vessels:

        print(f"Processing {vessel['vessel_name']}...")

        vessel_name = vessel["vessel_name"]
        imo_number = vessel["imo_number"]
        incoming_eta = normalize_eta(vessel["eta"])

        previous_state = get_vessel_state(vessel_name, imo_number)
        is_new_vessel = previous_state is None

        # new vessel pulled in by api has no operations seeded
        if is_new_vessel:
            inserted_as_active = save_new_vessel_observation(vessel, incoming_eta)
            # A staged row for a future operating day deliberately remains
            # invisible to active monitoring. Its primary-key conflict makes
            # this insert return False; do not assign resources before the
            # midnight activation job.
            if inserted_as_active is False:
                continue
        else:
            stored_current_eta = normalize_eta(previous_state["current_eta"])

            if incoming_eta != stored_current_eta:
                persisted_change = record_eta_change(vessel, incoming_eta)

                # Another monitor may have already recorded this ETA.
                if persisted_change is not None:
                    changes.append({
                        "event": "ETA_CHANGED",
                        "vessel_name": vessel_name,
                        "imo_number": imo_number,
                        "previous_eta": persisted_change["previous_eta"].isoformat(),
                        "new_eta": persisted_change["current_eta"].isoformat(),
                    })
            else:
                refresh_vessel_observation(vessel)

        # Ensure every vessel has a complete operational schedule during normal
        # monitoring. Midnight initialization disables this so the original
        # generate_operations() routine can size and assign the whole day.
        assigned = {}
        assignment_error = None
        if assign_operations:
            try:
                assigned = assign_initial_operations(
                    vessel_name, imo_number, incoming_eta, is_new_vessel, existing_allocation_keys
                )
            except Exception as error:
                # Don't let one failed assignment stop the monitoring poll.
                assignment_error = str(error)
                print(f"  Could not assign initial operations for {vessel_name} ({imo_number}): {error}")

        # Only a new vessel is reported as a change here; retried assignments
        # for an existing vessel's incomplete schedule happen silently.
        if is_new_vessel:
            changes.append({
                "event": "NEW_VESSEL_DISCOVERED",
                "vessel_name": vessel_name,
                "imo_number": imo_number,
                "eta": incoming_eta.isoformat(),
                "assigned": assigned,
                "assignment_error": assignment_error,
            })

    print("Monitoring complete.")
    if (len(changes) == 0):
        print("No changes since last update.")

    return changes


# Retry a vessel's unconfirmed assignments using the scheduling pipeline.
# Apply the best valid option (outcome: "resources_allocated"), or escalate
# to pending_review if none exists (outcome: "pending_review").
def retry_unconfirmed_operations(vessel_name, imo_number):
    schedule = get_vessel_schedule(vessel_name, imo_number)
    if schedule is None:
        return {
            "vessel_name": vessel_name, "imo_number": imo_number,
            "unconfirmed_resource_types": [], "outcome": "not_found",
            "applied": None, "escalated": [],
        }

    unconfirmed_types = [
        resource_type for resource_type, allocation in schedule["allocations"].items()
        if allocation is not None and allocation["status"] == "unconfirmed"
    ]
    if not unconfirmed_types:
        return {
            "vessel_name": vessel_name, "imo_number": imo_number,
            "unconfirmed_resource_types": [], "outcome": "no_action",
            "applied": None, "escalated": [],
        }

    eta = schedule["vessel"]["current_eta"]
    try:
        generated = generate_schedule_options(vessel_name, imo_number, eta)
        valid, invalid = filter_valid_options(generated)
        ranked = rank_options(valid)
    except ValueError as error:
        # Treat an incomplete schedule as having no valid option.
        ranked, invalid = [], [{"invalid_reason": str(error)}]

    if ranked:
        reason = (
            f"Automatically resolved unconfirmed {', '.join(unconfirmed_types)} "
            "assignment(s) found at discovery time."
        )
        applied = apply_schedule_option(ranked[0], reason, execution_mode="new_vessel_retry")
        return {
            "vessel_name": vessel_name, "imo_number": imo_number,
            "unconfirmed_resource_types": unconfirmed_types,
            "outcome": "resources_allocated" if applied["success"] else "apply_failed",
            "applied": applied, "escalated": [],
        }

    escalation_reason = invalid[0]["invalid_reason"] if invalid else "No valid scheduling option was found."
    escalated = [
        flag_allocation_for_review(resource_type, vessel_name, imo_number, escalation_reason)
        for resource_type in unconfirmed_types
    ]
    return {
        "vessel_name": vessel_name, "imo_number": imo_number,
        "unconfirmed_resource_types": unconfirmed_types,
        "outcome": "pending_review",
        "applied": None, "escalated": escalated,
    }
