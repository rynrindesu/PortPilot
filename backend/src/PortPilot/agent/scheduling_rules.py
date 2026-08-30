
from datetime import datetime, timedelta, timezone

from PortPilot.database.postgres import get_vessel_state

# Bookings within this window cannot be automatically rescheduled.
FREEZE_WINDOW_HOURS = 2

# Maps each resource type to its assignment table and ID column.
RESOURCE_TABLES = {
    "pilot": ("pilot_assignments", "pilot_id"),
    "tug": ("tug_assignments", "tug_id"),
    "berth": ("berth_allocations", "berth_id"),
}

# Soft-constraint ranking order. Earlier criteria have higher priority.
DEFAULT_PRIORITY = [
    "affected_vessel_count",
    "downstream_effects",
    "total_delay",
    "repeat_changes",
    "resource_utilisation",
]

# Return True if the booking has started or is within the freeze window.
def is_booking_locked(cursor, resource_type, vessel_name, imo_number):
    table, _resource_column = RESOURCE_TABLES[resource_type]

    cursor.execute(
        f"SELECT start_time FROM {table} WHERE vessel_name = %s AND imo_number = %s",
        (vessel_name, imo_number),
    )
    row = cursor.fetchone()

    # No existing booking means there is nothing to freeze.
    if row is None:
        return False

    start_time = row[0]
    return start_time < datetime.now(timezone.utc) + timedelta(hours=FREEZE_WINDOW_HOURS)

# Check whether the proposed resource slot is available.
# If disrupted vessels conflict for the same slot, use original ETA for FCFS priority.
def is_option_available(cursor, resource_type, resource_id, start, end, current_vessel, this_original_eta):
    # Check for confirmed bookings that overlap the proposed slot.
    table, resource_column = RESOURCE_TABLES[resource_type]
    vessel_name, imo_number = current_vessel

    cursor.execute(
        f"""
        SELECT vessel_name, imo_number FROM {table}
        WHERE {resource_column} = %s
          AND status = 'confirmed'
          AND start_time < %s
          AND end_time > %s
          AND NOT (vessel_name = %s AND imo_number = %s)
        """,
        (resource_id, end, start, vessel_name, imo_number),
    )
    conflicts = cursor.fetchall()

    # No overlap means the resource is immediately available.
    if not conflicts:
        return True

    for other_vessel_name, other_imo_number in conflicts:
        other_vessel = get_vessel_state(other_vessel_name, other_imo_number)
        
        # Cannot safely resolve the conflict without the vessel's ETA information.
        if other_vessel is None:
            return False

        other_disrupted = other_vessel["current_eta"] != other_vessel["original_eta"]

        # An undisturbed vessel keeps its existing booking.
        if not other_disrupted:
            return False

        # Between two disrupted vessels, the earlier original ETA gets priority.
        if other_vessel["original_eta"] < this_original_eta:
            return False

    # All conflicts are with disrupted vessels that have lower FCFS priority.
    return True

# Keep only candidates that pass the freeze window and availability / FCFS checks.
def filter_valid_options(cursor, candidates, resource_type, vessel_name, imo_number):
    current_vessel = (vessel_name, imo_number)

    # A frozen booking can't be touched at all, no candidate survives.
    if is_booking_locked(cursor, resource_type, vessel_name, imo_number):
        return []

    vessel = get_vessel_state(vessel_name, imo_number)
    if vessel is None:
        return []
    this_original_eta = vessel["original_eta"]

    valid = []
    for option in candidates:
        if is_option_available(
            cursor, resource_type, option["resource_id"],
            option["new_start"], option["new_end"],
            current_vessel, this_original_eta,
        ):
            valid.append(option)

    return valid