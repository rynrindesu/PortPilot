"""Deterministic generation of coordinated berth, pilot, and tug plan options.

This module does not call an LLM and never writes to the database. It creates
direct options for the affected vessel and may create one reallocation option
that moves the affected vessel plus one other eligible vessel.
"""

from datetime import datetime, timedelta, timezone
from itertools import product

from PortPilot.database.postgres import (
    get_active_resources,
    get_allocations_in_window,
    get_vessel_schedule,
)


RESOURCE_TYPES = ("berth", "pilot", "tug")
FREEZE_WINDOW = timedelta(hours=2)
PLANNING_LOOKBACK = timedelta(hours=2)
PLANNING_LOOKAHEAD = timedelta(hours=24)
MAX_DIRECT_OPTIONS = 20
MAX_REALLOCATION_OPTIONS = 10


def _vessel_key(vessel_name, imo_number):
    return vessel_name, imo_number


def _ensure_complete_schedule(schedule):
    if schedule is None:
        raise ValueError("Vessel state was not found.")
    missing = [
        resource_type
        for resource_type, allocation in schedule["allocations"].items()
        if allocation is None
    ]
    if missing:
        raise ValueError(f"Vessel is missing allocation(s): {', '.join(missing)}.")


def _build_plan(schedule, target_eta, resource_ids):
    """Preserve seeded operation durations while centring the plan on target ETA."""
    allocations = {}
    for resource_type in RESOURCE_TYPES:
        template = schedule["allocations"][resource_type]
        duration = template["end_time"] - template["start_time"]

        if resource_type == "pilot":
            start_time, end_time = target_eta - duration, target_eta
        else:
            start_time, end_time = target_eta, target_eta + duration

        allocations[resource_type] = {
            "resource_id": resource_ids[resource_type],
            "start_time": start_time,
            "end_time": end_time,
            "buffer_minutes": template["buffer_minutes"],
        }
    return allocations


def _current_plan(schedule):
    return {
        resource_type: {
            "resource_id": allocation["resource_id"],
            "start_time": allocation["start_time"],
            "end_time": allocation["end_time"],
            "buffer_minutes": allocation["buffer_minutes"],
        }
        for resource_type, allocation in schedule["allocations"].items()
    }


def _plans_overlap(left, right):
    """Return true if plans contend for any same resource, including buffers."""
    for resource_type in RESOURCE_TYPES:
        left_item = left[resource_type]
        right_item = right[resource_type]
        if left_item["resource_id"] != right_item["resource_id"]:
            continue
        left_occupied_end = left_item["end_time"] + timedelta(
            minutes=left_item["buffer_minutes"]
        )
        right_occupied_end = right_item["end_time"] + timedelta(
            minutes=right_item["buffer_minutes"]
        )
        if left_item["start_time"] < right_occupied_end and right_item["start_time"] < left_occupied_end:
            return True
    return False


def _conflicts_for_plan(plan, allocations, ignored_vessels):
    conflicts = []
    for booking in allocations:
        if _vessel_key(booking["vessel_name"], booking["imo_number"]) in ignored_vessels:
            continue

        candidate = plan[booking["resource_type"]]
        if candidate["resource_id"] != booking["resource_id"]:
            continue

        candidate_occupied_end = candidate["end_time"] + timedelta(
            minutes=candidate["buffer_minutes"]
        )
        booking_occupied_end = booking["end_time"] + timedelta(
            minutes=booking["buffer_minutes"]
        )
        if candidate["start_time"] < booking_occupied_end and booking["start_time"] < candidate_occupied_end:
            conflicts.append(booking)
    return conflicts


def _resource_combinations(resources):
    if any(not resources.get(resource_type) for resource_type in RESOURCE_TYPES):
        return []
    return (
        dict(zip(RESOURCE_TYPES, resource_ids, strict=True))
        for resource_ids in product(*(resources[resource_type] for resource_type in RESOURCE_TYPES))
    )


def _candidate(option_id, strategy, target_eta, changes, conflicts=None):
    return {
        "option_id": option_id,
        "strategy": strategy,
        "target_eta": target_eta,
        "affected_vessels": [
            {"vessel_name": change["vessel_name"], "imo_number": change["imo_number"]}
            for change in changes
        ],
        "changes": changes,
        "resource_conflicts": conflicts or [],
    }


def _change(vessel_name, imo_number, allocations):
    return {
        "vessel_name": vessel_name,
        "imo_number": imo_number,
        "allocations": allocations,
    }


def _find_reallocation_plan(
    displaced_schedule,
    displaced_key,
    target_plan,
    allocations,
    resources,
    ignored_vessels,
):
    """Find a conflict-free replacement plan for one displaced vessel."""
    target_eta = displaced_schedule["vessel"]["current_eta"]
    for resource_ids in _resource_combinations(resources):
        plan = _build_plan(displaced_schedule, target_eta, resource_ids)
        conflicts = _conflicts_for_plan(plan, allocations, ignored_vessels | {displaced_key})
        if not conflicts and not _plans_overlap(plan, target_plan):
            return plan
    return None


def generate_schedule_options(vessel_name, imo_number, new_eta, now=None):
    """Generate direct and one-vessel-reallocation plans for a revised ETA.

    The result is intentionally not ranked and is not a final feasibility
    decision. The later validation and scoring stages apply FCFS and other
    policy rules before any write can occur.
    """
    if new_eta.tzinfo is None:
        raise ValueError("new_eta must include a timezone.")
    new_eta = new_eta.astimezone(timezone.utc)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    affected_schedule = get_vessel_schedule(vessel_name, imo_number)
    _ensure_complete_schedule(affected_schedule)
    affected_key = _vessel_key(vessel_name, imo_number)
    resources = get_active_resources()
    window_start = new_eta - PLANNING_LOOKBACK
    window_end = new_eta + PLANNING_LOOKAHEAD
    surrounding_allocations = get_allocations_in_window(window_start, window_end)

    options = [
        _candidate(
            "retain_current_allocation",
            "retain_current_allocation",
            new_eta,
            [_change(vessel_name, imo_number, _current_plan(affected_schedule))],
        )
    ]

    current_resource_ids = {
        resource_type: affected_schedule["allocations"][resource_type]["resource_id"]
        for resource_type in RESOURCE_TYPES
    }
    same_resource_plan = _build_plan(affected_schedule, new_eta, current_resource_ids)
    same_resource_conflicts = _conflicts_for_plan(
        same_resource_plan, surrounding_allocations, {affected_key}
    )
    if not same_resource_conflicts:
        options.append(
            _candidate(
                "shift_same_resources",
                "shift_same_resources",
                new_eta,
                [_change(vessel_name, imo_number, same_resource_plan)],
            )
        )

    direct_options = []
    reallocation_options = []
    seen_resource_sets = {tuple(current_resource_ids[resource_type] for resource_type in RESOURCE_TYPES)}
    displaced_schedules = {}

    for resource_ids in _resource_combinations(resources):
        resource_set = tuple(resource_ids[resource_type] for resource_type in RESOURCE_TYPES)
        if resource_set in seen_resource_sets:
            continue
        seen_resource_sets.add(resource_set)
        target_plan = _build_plan(affected_schedule, new_eta, resource_ids)
        conflicts = _conflicts_for_plan(target_plan, surrounding_allocations, {affected_key})

        if not conflicts:
            direct_options.append(
                _candidate(
                    f"alternative_resources_{len(direct_options) + 1}",
                    "alternative_resources",
                    new_eta,
                    [_change(vessel_name, imo_number, target_plan)],
                )
            )
            if len(direct_options) >= MAX_DIRECT_OPTIONS:
                break
            continue

        displaced_keys = {
            _vessel_key(conflict["vessel_name"], conflict["imo_number"])
            for conflict in conflicts
        }
        if len(displaced_keys) != 1 or len(reallocation_options) >= MAX_REALLOCATION_OPTIONS:
            continue

        displaced_key = displaced_keys.pop()
        if displaced_key not in displaced_schedules:
            displaced_schedules[displaced_key] = get_vessel_schedule(*displaced_key)
        displaced_schedule = displaced_schedules[displaced_key]
        try:
            _ensure_complete_schedule(displaced_schedule)
        except ValueError:
            continue

        if displaced_schedule["vessel"]["current_eta"] <= now + FREEZE_WINDOW:
            continue

        displaced_plan = _find_reallocation_plan(
            displaced_schedule,
            displaced_key,
            target_plan,
            surrounding_allocations,
            resources,
            {affected_key},
        )
        if displaced_plan is None:
            continue

        reallocation_options.append(
            _candidate(
                f"reallocate_one_vessel_{len(reallocation_options) + 1}",
                "reallocate_one_vessel",
                new_eta,
                [
                    _change(vessel_name, imo_number, target_plan),
                    _change(displaced_key[0], displaced_key[1], displaced_plan),
                ],
                conflicts,
            )
        )

    return options + direct_options + reallocation_options
