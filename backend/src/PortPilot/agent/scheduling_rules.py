from datetime import datetime, timedelta, timezone

from PortPilot.database.postgres import (
    get_vessel_schedule,
    find_resource_conflicts,
    get_active_resources,
)

# Bookings within this window cannot be automatically rescheduled.
FREEZE_WINDOW_HOURS = 2

# Soft-constraint ranking order. Earlier criteria have higher priority.
# Use later when implementing the scoring logic.
DEFAULT_PRIORITY = [
    "affected_vessel_count",
    "downstream_effects",
    "total_delay",
    "repeat_changes",
    "resource_utilisation",
]

# Check whether the proposed allocation keeps the current booking unchanged.
# Unchanged bookings are allowed even within the freeze window.
def _is_unchanged(current, proposed):
    return (
        current is not None
        and current["resource_id"] == proposed["resource_id"]
        and current["start_time"] == proposed["start_time"]
        and current["end_time"] == proposed["end_time"]
    )


# Check whether an existing allocation is already in progress or too
# close to its start time to be automatically reassigned.
def is_booking_locked(current_allocation, now=None):
    if current_allocation is None:
        return False
    now = now or datetime.now(timezone.utc)
    return current_allocation["start_time"] < now + timedelta(hours=FREEZE_WINDOW_HOURS)


# Check whether a proposed resource slot can be used.
#
# If the slot conflicts with another vessel, apply FCFS rules:
# - invalid: the other vessel cannot be displaced
# - available: the slot can be used
#
# must_reallocate contains any displaced vessels that still need
# a replacement for this resource.
def is_option_available(resource_type, resource_id, start, end, buffer_minutes,
                         current_vessel, candidate_vessels, this_original_eta):
    # Find existing database bookings that overlap the proposed slot.
    conflicts = find_resource_conflicts(
        resource_type, resource_id, start, end,
        candidate_buffer_minutes=buffer_minutes,
    )

    # Apply FCFS rules to determine whether these conflicts block the move
    # or require another vessel to be reallocated.
    rejection_reason, must_reallocate = resolve_fcfs(
        conflicts, this_original_eta, current_vessel, candidate_vessels, resource_type,
    )

    # A hard FCFS or non-disrupted-vessel conflict makes the option invalid.
    if rejection_reason is not None:
        return "invalid", rejection_reason, []

    return "available", None, must_reallocate


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
                        f"{vessel_a} and {vessel_b} both propose {resource_type} "
                        f"{resource_id} at overlapping times within the same candidate"
                    )
    return None


# Build the time window for a displaced vessel's replacement resource.
# Keep the vessel at its current ETA and preserve the original duration
# and buffer of that resource allocation.
def _build_replacement_allocation(schedule, resource_type):
    template = schedule["allocations"][resource_type]
    duration = template["end_time"] - template["start_time"]
    target_eta = schedule["vessel"]["current_eta"]

    # Pilot work finishes at ETA; berth and tug work start at ETA.
    if resource_type == "pilot":
        start_time, end_time = target_eta - duration, target_eta
    else:
        start_time, end_time = target_eta, target_eta + duration

    return start_time, end_time, template["buffer_minutes"]


# Check whether this replacement would conflict with another allocation
# already proposed inside the same candidate.
def _conflicts_with_changes(resource_type, resource_id, start, end, buffer_minutes, changes):
    candidate = {"start_time": start, "end_time": end, "buffer_minutes": buffer_minutes}
    for change in changes:
        allocation = change["allocations"].get(resource_type)
        if allocation is not None and allocation["resource_id"] == resource_id:
            if _allocations_overlap(candidate, allocation):
                return True
    return False


# Find a free replacement resource for a displaced vessel.
#
# The replacement:
# - keeps the vessel at its current ETA
# - must use an active resource
# - must not conflict with existing database bookings
# - must not conflict with other changes in this candidate
#
# Return the first feasible replacement, or None if none is available.
def _find_replacement_allocation(vessel_key, resource_type, changes):
    schedule = get_vessel_schedule(*vessel_key)
    if schedule is None:
        return None

    # A frozen allocation cannot be moved.
    if is_booking_locked(schedule["allocations"].get(resource_type)):
        return None

    start_time, end_time, buffer_minutes = _build_replacement_allocation(schedule, resource_type)

    # Try each active resource until a conflict-free replacement is found.
    for resource_id in get_active_resources().get(resource_type, []):
        conflicts = find_resource_conflicts(
            resource_type, resource_id, start_time, end_time,
            candidate_buffer_minutes=buffer_minutes,
            exclude_vessel_name=vessel_key[0],
            exclude_imo_number=vessel_key[1],
        )
        
        # Skip resources already occupied by another vessel.
        if conflicts:
            continue
        
        # Also skip resources that clash with new allocations in this candidate.
        if _conflicts_with_changes(resource_type, resource_id, start_time, end_time, buffer_minutes, changes):
            continue

        return {
            "resource_id": resource_id,
            "start_time": start_time,
            "end_time": end_time,
            "buffer_minutes": buffer_minutes,
        }

    return None


# Validate one complete scheduling candidate.
#
# For each proposed allocation:
# 1. Check that the existing booking is not frozen.
# 2. Check resource conflicts and apply FCFS.
# 3. If another vessel is displaced, find it a replacement resource.
# 4. Add successful replacements to the same candidate and validate them too.
#
# The candidate is valid only when every proposed change and replacement
# passes all checks.
def _classify_option(option):
    changes = list(option["changes"])
    # Track replacements by vessel AND resource type.
    # A vessel is only considered covered if the displaced resource itself
    # has a replacement.
    candidate_vessels = {
        (change["vessel_name"], change["imo_number"], resource_type)
        for change in changes
        for resource_type in change["allocations"]
    }

    # Use a while loop because reallocation can add new changes while validating.
    # Newly added replacements will also be checked before the candidate is valid.
    i = 0
    while i < len(changes):
        change = changes[i]
        vessel_name = change["vessel_name"]
        imo_number = change["imo_number"]
        current_vessel = (vessel_name, imo_number)

        schedule = get_vessel_schedule(vessel_name, imo_number)
        if schedule is None:
            return "invalid", f"No existing schedule found for {vessel_name} ({imo_number})", changes

        # FCFS always compares original ETAs, not revised/proposed ETAs.
        this_original_eta = schedule["vessel"]["original_eta"]

        for resource_type, allocation in change["allocations"].items():
            current = schedule["allocations"].get(resource_type)

            # Freeze rules only block changes to an existing booking.
            if not _is_unchanged(current, allocation) and is_booking_locked(current):
                return "invalid", (
                    f"{vessel_name}'s {resource_type} booking starts within "
                    f"{FREEZE_WINDOW_HOURS}h and cannot be reassigned"
                ), changes

            # Check database conflicts and FCFS eligibility for this allocation.
            status, reason, must_reallocate = is_option_available(
                resource_type, allocation["resource_id"],
                allocation["start_time"], allocation["end_time"],
                allocation["buffer_minutes"],
                current_vessel, candidate_vessels, this_original_eta,
            )
            if status == "invalid":
                return "invalid", f"{vessel_name}'s {reason}", changes

            # This allocation displaces other vessels - try to find each one
            # a free replacement slot right now, instead of retrying later.
            # resolve_fcfs already excludes vessels that already have a
            # replacement allocation for this specific resource_type.
            for displaced_key in must_reallocate:
                replacement = _find_replacement_allocation(displaced_key, resource_type, changes)
                if replacement is None:
                    return "invalid", (
                        f"{vessel_name}'s {resource_type} slot displaces "
                        f"{displaced_key[0]} ({displaced_key[1]}), who has no "
                        f"available replacement slot"
                    ), changes

                # Add the replacement to this candidate so it is also validated.
                changes.append({
                    "vessel_name": displaced_key[0],
                    "imo_number": displaced_key[1],
                    "allocations": {resource_type: replacement},
                })
                candidate_vessels.add((displaced_key[0], displaced_key[1], resource_type))

        i += 1

    # After all reallocations are added, make sure the proposed changes
    # do not conflict with each other.
    internal_reason = _find_internal_conflict(changes)
    if internal_reason is not None:
        return "invalid", internal_reason, changes

    return "valid", None, changes


# Validate all generated candidates and separate them into valid and invalid.
# Valid candidates include any replacement allocations added during validation.
def filter_valid_options(options):
    valid = []
    invalid = []

    for option in options:
        status, reason, changes = _classify_option(option)
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


# Apply FCFS when a proposed allocation conflicts with another vessel.
#
# Rules:
# 1. Ignore the vessel's own existing booking.
# 2. A vessel without an ETA change cannot be displaced.
# 3. If both vessels are disrupted, compare their original ETAs.
# 4. The vessel with the earlier original ETA keeps priority.
# 5. If the current vessel has priority, the other vessel must have
#    a replacement for the displaced resource.
#
# Returns:
# - rejection_reason: why the allocation is blocked, or None
# - must_reallocate: vessels that are allowed to be displaced but
#   still need replacement allocations
def resolve_fcfs(conflicts, this_original_eta, current_vessel, candidate_vessels, resource_type):
    must_reallocate = []

    for booking in conflicts:
        conflict_key = (booking["vessel_name"], booking["imo_number"])

        # Ignore this vessel's own existing booking.
        # The candidate will replace it if the allocation changes.
        if conflict_key == current_vessel:
            continue

        other_schedule = get_vessel_schedule(*conflict_key)

        if other_schedule is None:
            return (
                f"No existing schedule found for {booking['vessel_name']} "
                f"({booking['imo_number']}).",
                [],
            )

        other_vessel = other_schedule["vessel"]

        # A vessel without an ETA revision keeps its existing allocation.
        if not _is_disrupted(other_vessel):
            return (
                f"Conflicts with {booking['vessel_name']}'s existing "
                f"{resource_type} booking, which has no ETA "
                f"change and cannot be displaced.",
                [],
            )

        # Among disrupted vessels, the earlier original ETA has FCFS priority.
        if other_vessel["original_eta"] < this_original_eta:
            return (
                f"{booking['vessel_name']} has an earlier original ETA and "
                f"therefore FCFS priority for this {resource_type} slot.",
                [],
            )

        # The current vessel has FCFS priority over this conflicting vessel.

        # A replacement for this exact resource_type is already included
        # in this same candidate.
        if (conflict_key[0], conflict_key[1], resource_type) in candidate_vessels:
            continue

        # It is not yet covered, so the candidate is incomplete.
        must_reallocate.append(conflict_key)

    return None, must_reallocate
