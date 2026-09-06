"""Deterministic scheduling logic for port-call rescheduling.

This module does not use an LLM or modify the database. It validates and
ranks scheduling candidates generated for a disrupted vessel.

1. Hard-constraint filtering validates candidates against the freeze window,
   resource conflicts, FCFS rules, and conflicts within the candidate.

2. Soft-constraint scoring ranks valid candidates using DEFAULT_PRIORITY,
   with the best option ranked first.
"""

from datetime import datetime, timedelta, timezone
from functools import lru_cache

from PortPilot.database.postgres import (
    get_vessel_schedule,
    get_allocations_in_window,
    get_connection,
    index_allocations_by_resource,
)

# Bookings within this window cannot be automatically rescheduled.
FREEZE_WINDOW_HOURS = 2

# Soft-constraint ranking order. Earlier criteria have higher priority.
# Use later when implementing the scoring logic.

# First minimize the number of vessels affected, 
# then minimize how far schedules are shifted, 
# then avoid repeatedly changing the same vessels, 
# and finally, when those are equal, prefer the option 
# with better schedule compactness by leaving less idle time between resource bookings.
DEFAULT_PRIORITY = [
    "affected_vessel_count",
    "total_schedule_shift",
    "repeat_changes",
    "resource_utilisation",
]


# --- Hard-constraint filtering -------------------------------------------
#
# Validate candidates against scheduling constraints and separate them
# into valid and invalid options.

# Check whether the proposed allocation keeps the current booking unchanged.
# Unchanged bookings are allowed even within the freeze window.
def _is_unchanged(current, proposed):
    return (
        current is not None
        and current["resource_id"] == proposed["resource_id"]
        and current["start_time"] == proposed["start_time"]
        and current["end_time"] == proposed["end_time"]
    )


# Check whether retained resource timings are still feasible
# against the vessel's revised ETA.
def _is_retain_timing_feasible(option):
    if option["strategy"] != "retain_current_allocation":
        return True

    target_eta = option["target_eta"]
    allocations = option["changes"][0]["allocations"]

    if allocations["pilot"]["end_time"] < target_eta:
        return False
    if allocations["tug"]["start_time"] < target_eta:
        return False
    if allocations["berth"]["start_time"] < target_eta:
        return False

    return True


# Check whether an existing allocation is already in progress or too
# close to its start time to be automatically reassigned.
def is_booking_locked(current_allocation, now=None):
    if current_allocation is None:
        return False
    now = now or datetime.now(timezone.utc)
    return current_allocation["start_time"] < now + timedelta(hours=FREEZE_WINDOW_HOURS)


# Find conflicting bookings from the pre-fetched resource index.
def _conflicts_from_index(allocations_by_resource, resource_type, resource_id,
                           start, end, buffer_minutes):
    candidate_occupied_end = end + timedelta(minutes=buffer_minutes)
    conflicts = []
    for booking in allocations_by_resource.get((resource_type, resource_id), []):
        booking_occupied_end = booking["end_time"] + timedelta(minutes=booking["buffer_minutes"])
        if start < booking_occupied_end and booking["start_time"] < candidate_occupied_end:
            conflicts.append(booking)
    return conflicts


# Check whether a proposed resource slot can be used.
#
# If the slot conflicts with another vessel, apply FCFS rules:
# - invalid: the conflicting vessel keeps its slot (it isn't disrupted, or
#   it has an earlier original ETA)
# - available: no conflict, or the conflict is already covered by a
#   replacement bundled into this same candidate
#
# Conflicts are checked using pre-fetched allocations and cached schedules.
def is_option_available(resource_type, resource_id, start, end, buffer_minutes,
                         current_vessel, candidate_vessels, this_original_eta,
                         allocations_by_resource, schedule_lookup):
    # Find bookings that overlap the proposed slot.
    conflicts = _conflicts_from_index(
        allocations_by_resource, resource_type, resource_id, start, end, buffer_minutes,
    )

    # Apply FCFS rules to determine whether these conflicts block the move.
    rejection_reason = resolve_fcfs(
        conflicts, this_original_eta, current_vessel, candidate_vessels, resource_type,
        schedule_lookup,
    )

    # A conflict that cannot be resolved under the scheduling rules
    # makes the option invalid.
    if rejection_reason is not None:
        return "invalid", rejection_reason

    return "available", None


# Return the effective end of an allocation, including its resource buffer.
def _occupied_end(allocation):
    return allocation["end_time"] + timedelta(minutes=allocation["buffer_minutes"])


# Check whether two allocations overlap, including their buffer time.
def _allocations_overlap(a, b):
    return a["start_time"] < _occupied_end(b) and b["start_time"] < _occupied_end(a)


# Check for conflicts between allocations proposed inside the same candidate.
# These cannot be found from the database because they have not been applied yet.
def _find_internal_conflict(changes):
    by_resource = {}

    # Group allocations that use the same resource.
    for change in changes:
        for resource_type, allocation in change["allocations"].items():
            key = (resource_type, allocation["resource_id"])
            by_resource.setdefault(key, []).append((change["vessel_name"], allocation))

    # Check each pair using the same resource for overlapping times.
    for (resource_type, resource_id), entries in by_resource.items():
        for i in range(len(entries)):
            vessel_a, alloc_a = entries[i]
            for vessel_b, alloc_b in entries[i + 1:]:
                if _allocations_overlap(alloc_a, alloc_b):
                    return (
                        f"{vessel_a} and {vessel_b} are assigned overlapping times on "
                        f"{resource_type} {resource_id} within the same candidate."
                    )
    return None


# Validate one complete scheduling candidate.
#
# Checks:
# 1. Retained timings remain feasible for the revised ETA.
# 2. Changed bookings are outside the freeze window.
# 3. Resource conflicts satisfy FCFS rules.
# 4. Proposed changes do not conflict with each other.
def _classify_option(option, schedule_lookup, allocations_by_resource):
    if not _is_retain_timing_feasible(option):
        return "invalid", (
            "Current allocation timing is no longer feasible with the revised ETA."
        ), option["changes"]

    changes = option["changes"]

    candidate_vessels = {
        (change["vessel_name"], change["imo_number"], resource_type)
        for change in changes
        for resource_type in change["allocations"]
    }

    for change in changes:
        vessel_name = change["vessel_name"]
        imo_number = change["imo_number"]
        current_vessel = (vessel_name, imo_number)

        schedule = schedule_lookup(vessel_name, imo_number)
        if schedule is None:
            return "invalid", f"No existing schedule was found for {vessel_name} ({imo_number}).", changes

        # FCFS always compares original ETAs, not revised/proposed ETAs.
        this_original_eta = schedule["vessel"]["original_eta"]

        for resource_type, allocation in change["allocations"].items():
            current = schedule["allocations"].get(resource_type)

            # Freeze rules only block changes to an existing booking.
            if not _is_unchanged(current, allocation) and is_booking_locked(current):
                return "invalid", (
                    f"{vessel_name}'s {resource_type} booking starts within the "
                    f"{FREEZE_WINDOW_HOURS}-hour freeze window and cannot be reassigned."
                ), changes

            # Check conflicts and FCFS eligibility for this allocation. Any
            # conflict not already covered by candidate_vessels rejects the
            # candidate.
            status, reason = is_option_available(
                resource_type, allocation["resource_id"],
                allocation["start_time"], allocation["end_time"],
                allocation["buffer_minutes"],
                current_vessel, candidate_vessels, this_original_eta,
                allocations_by_resource, schedule_lookup,
            )
            if status == "invalid":
                return "invalid", reason, changes

    # Make sure the proposed changes do not conflict with each other.
    internal_reason = _find_internal_conflict(changes)
    if internal_reason is not None:
        return "invalid", internal_reason, changes

    return "valid", None, changes


# Extra margin for candidate buffer time when bulk-fetching conflicts.
# Long-running bookings are still captured by the overlap query.
_FILTER_WINDOW_MARGIN = timedelta(hours=2)


# Return the time range covered by all allocations in the candidate options.
def _options_time_range(options):
    times = [
        allocation[field]
        for option in options
        for change in option["changes"]
        for allocation in change["allocations"].values()
        for field in ("start_time", "end_time")
    ]
    if not times:
        return None
    return min(times), max(times)


# Validate generated candidates and separate them into valid and invalid options.
#
# Relevant bookings are bulk-fetched once, and vessel schedules are cached
# and reused across all candidates.
def filter_valid_options(options):
    # A fresh cache per call - scoped to this batch of options only.
    schedule_lookup = lru_cache(maxsize=None)(get_vessel_schedule)

    time_range = _options_time_range(options)
    if time_range is not None:
        window_start = time_range[0] - _FILTER_WINDOW_MARGIN
        window_end = time_range[1] + _FILTER_WINDOW_MARGIN
        allocations_by_resource = index_allocations_by_resource(
            get_allocations_in_window(window_start, window_end)
        )
    else:
        allocations_by_resource = {}

    valid = []
    invalid = []

    for option in options:
        status, reason, changes = _classify_option(option, schedule_lookup, allocations_by_resource)
        if status == "valid":
            affected_vessels = [
                {"vessel_name": change["vessel_name"], "imo_number": change["imo_number"]}
                for change in changes
            ]
            valid.append({**option, "changes": changes, "affected_vessels": affected_vessels})
        else:
            invalid.append({**option, "invalid_reason": reason})

    return valid, invalid


# Return True if the vessel's ETA has changed from its original ETA.
def _is_disrupted(vessel):
    return vessel["current_eta"] != vessel["original_eta"]


# Apply FCFS rules when a proposed allocation conflicts with another vessel.
# Returns a rejection reason if the conflict blocks the candidate.
def resolve_fcfs(conflicts, this_original_eta, current_vessel, candidate_vessels, resource_type,
                  schedule_lookup=None):
    if schedule_lookup is None:
        schedule_lookup = get_vessel_schedule

    for booking in conflicts:
        conflict_key = (booking["vessel_name"], booking["imo_number"])

        # Ignore this vessel's own existing booking.
        # The candidate will replace it if the allocation changes.
        if conflict_key == current_vessel:
            continue

        if (conflict_key[0], conflict_key[1], resource_type) in candidate_vessels:
            continue

        other_schedule = schedule_lookup(*conflict_key)

        if other_schedule is None:
            return (
                f"No existing schedule found for {booking['vessel_name']} "
                f"({booking['imo_number']})."
            )

        other_vessel = other_schedule["vessel"]

        # Among disrupted vessels, the earlier original ETA has priority -
        # this vessel loses FCFS and is rejected, never reallocated.
        if _is_disrupted(other_vessel) and other_vessel["original_eta"] < this_original_eta:
            return (
                f"{booking['vessel_name']} has an earlier original ETA and "
                f"therefore FCFS priority for this {resource_type} slot."
            )

        if not _is_disrupted(other_vessel):
            return (
                f"{booking['vessel_name']} has an unchanged schedule and keeps its "
                f"{resource_type} slot."
            )
        return (
            f"{booking['vessel_name']}'s {resource_type} booking conflicts with this "
            f"candidate and was not already covered by a replacement in it."
        )

    return None


# --- Soft-constraint scoring -------------------------------------------
#
# Each scorer returns a value for one priority criterion.
# Lower values are better.

# Count the unique vessels changed by this option.
# Fewer affected vessels are preferred. Takes no database data, but accepts
# context for a uniform scorer signature (see _SCORERS/_score_option).
def _affected_vessel_count(option, context=None):
    return len({(v["vessel_name"], v["imo_number"]) for v in option["affected_vessels"]})


# Calculate the total schedule shift across all changed allocations.
# Smaller shifts from the current schedule are preferred.
def _total_schedule_shift(option, context=None):
    schedule_lookup = context["schedule_lookup"] if context else get_vessel_schedule

    total = timedelta()
    for change in option["changes"]:
        # Get the vessel's current schedule for comparison.
        schedule = schedule_lookup(change["vessel_name"], change["imo_number"])

        if schedule is None:
            continue
        
        for resource_type, allocation in change["allocations"].items():
            # Get the current allocation for the same resource type.
            current = schedule["allocations"].get(resource_type)
            if current is None:
                continue
            
            # Count how far the allocation moves, whether earlier or later.
            total += abs(allocation["start_time"] - current["start_time"])
    
    # Return the total schedule shift in minutes.
    return total.total_seconds() / 60


# Return how many times one vessel's ETA has already been revised.
def _count_previous_changes(vessel_name, imo_number):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM eta_history WHERE vessel_name = %s AND imo_number = %s",
                (vessel_name, imo_number),
            )
            return cursor.fetchone()[0]


# Count previous ETA changes across all vessels affected by the option.
# Fewer repeat changes are preferred.
def _repeat_changes(option, context=None):
    repeat_count_lookup = context["repeat_count_lookup"] if context else _count_previous_changes
    vessels = {(change["vessel_name"], change["imo_number"]) for change in option["changes"]}
    return sum(repeat_count_lookup(vessel_name, imo_number) for vessel_name, imo_number in vessels)


# How far this candidate's window looks for a neighbouring booking on the
# same resource when measuring idle time. 
# Wide enough to catch the next booking in a typical port schedule without scanning the whole day.
RESOURCE_UTILISATION_WINDOW = timedelta(hours=6)


# Find bookings for a resource within the given window.
# Use the pre-fetched resource index when available.
def _bookings_in_window(context, resource_type, resource_id, window_start, window_end):
    if context is None:
        return [
            booking for booking in get_allocations_in_window(window_start, window_end)
            if booking["resource_type"] == resource_type and booking["resource_id"] == resource_id
        ]
    bucket = context["allocations_by_resource"].get((resource_type, resource_id), [])
    return [
        booking for booking in bucket
        if booking["start_time"] < window_end
        and booking["end_time"] + timedelta(minutes=booking["buffer_minutes"]) > window_start
    ]


# Measure idle time between proposed allocations and the next booking.
# Less idle time indicates better resource utilisation.
def _resource_utilisation(option, context=None):
    # Track existing bookings replaced by this candidate.
    replaced_vessel_resources = {
        (change["vessel_name"], change["imo_number"], resource_type)
        for change in option["changes"]
        for resource_type in change["allocations"]
    }

    # Flatten all proposed allocations for comparison with DB bookings.
    proposed_bookings = [
        {
            "resource_type": resource_type,
            "resource_id": allocation["resource_id"],
            "vessel_name": change["vessel_name"],
            "imo_number": change["imo_number"],
            "start_time": allocation["start_time"],
        }
        for change in option["changes"]
        for resource_type, allocation in change["allocations"].items()
    ]

    total_idle = timedelta()

    for change in option["changes"]:
        vessel_key = (change["vessel_name"], change["imo_number"])
        for resource_type, allocation in change["allocations"].items():
            occupied_end = allocation["end_time"] + timedelta(minutes=allocation["buffer_minutes"])
            window_start = allocation["start_time"] - RESOURCE_UTILISATION_WINDOW
            window_end = occupied_end + RESOURCE_UTILISATION_WINDOW

            # Remove DB bookings replaced by this candidate.
            db_bookings = [
                booking
                for booking in _bookings_in_window(
                    context, resource_type, allocation["resource_id"], window_start, window_end,
                )
                if (booking["vessel_name"], booking["imo_number"], booking["resource_type"])
                not in replaced_vessel_resources
            ]

            # Consider proposed bookings after this allocation finishes,
            # within this allocation's search window.
            candidate_bookings = [
                booking for booking in proposed_bookings
                if occupied_end <= booking["start_time"] <= window_end
            ]

            next_start = min(
                (
                    booking["start_time"]
                    for booking in db_bookings + candidate_bookings
                    if booking["resource_type"] == resource_type
                    and booking["resource_id"] == allocation["resource_id"]
                    and (booking["vessel_name"], booking["imo_number"]) != vessel_key
                    and booking["start_time"] >= occupied_end
                ),
                default=None,
            )
            if next_start is not None:
                total_idle += next_start - occupied_end
            else:
                # No next booking means the full window counts as idle time.
                total_idle += RESOURCE_UTILISATION_WINDOW

    return total_idle.total_seconds() / 60


# Maps each DEFAULT_PRIORITY criterion name to the function that scores it.
_SCORERS = {
    "affected_vessel_count": _affected_vessel_count,
    "total_schedule_shift": _total_schedule_shift,
    "repeat_changes": _repeat_changes,
    "resource_utilisation": _resource_utilisation,
}


# Calculate an option's scores and build its ranking key.
# Lower values are better, with earlier criteria taking priority.
def _score_option(option, context=None):
    scores = {criterion: _SCORERS[criterion](option, context) for criterion in DEFAULT_PRIORITY}
    sort_key = tuple(scores[criterion] for criterion in DEFAULT_PRIORITY)
    return sort_key, scores


# Extra margin when bulk-fetching bookings used for resource utilisation scoring.
_RANKING_WINDOW_MARGIN = timedelta(hours=1)


# Build shared data used to rank all options.
# Caches vessel schedules and ETA change counts, and bulk-fetches
# relevant bookings for resource utilisation scoring.
def _build_ranking_context(options):
    # Fresh caches per call - scoped to this batch of options only.
    schedule_lookup = lru_cache(maxsize=None)(get_vessel_schedule)
    repeat_count_lookup = lru_cache(maxsize=None)(_count_previous_changes)

    time_range = _options_time_range(options)
    if time_range is not None:
        margin = RESOURCE_UTILISATION_WINDOW + _RANKING_WINDOW_MARGIN
        allocations_by_resource = index_allocations_by_resource(
            get_allocations_in_window(time_range[0] - margin, time_range[1] + margin)
        )
    else:
        allocations_by_resource = {}

    return {
        "schedule_lookup": schedule_lookup,
        "repeat_count_lookup": repeat_count_lookup,
        "allocations_by_resource": allocations_by_resource,
    }


# Rank valid options from best to worst using DEFAULT_PRIORITY.
def rank_options(valid_options):
    context = _build_ranking_context(valid_options)

    scored = sorted(
        (( *_score_option(option, context), option) for option in valid_options),
        key=lambda item: item[0],
    )

    return [
        {**option, "rank": rank, "scores": scores}
        for rank, (_, scores, option) in enumerate(scored, start=1)
    ]
