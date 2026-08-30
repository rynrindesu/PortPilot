from PortPilot.integration.oceans import get_vessels_due_to_arrive
from datetime import datetime, timezone

from PortPilot.database.postgres import (
    get_vessel_state,
    record_eta_change,
    refresh_vessel_observation,
    save_new_vessel_observation,
)

def normalize_eta(value):
    if isinstance(value, datetime):
        eta = value
    else:
        eta = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if eta.tzinfo is None:
        eta = eta.replace(tzinfo=timezone.utc)

    return eta.astimezone(timezone.utc)


def monitor_vessels(date):
    print("Fetching OCEANS-X data...")
    current_vessels = get_vessels_due_to_arrive(date)
    print(f"Received {len(current_vessels)} vessels.")

    changes = []

    for vessel in current_vessels:

        print(f"Processing {vessel['vessel_name']}...")

        vessel_name = vessel["vessel_name"]
        imo_number = vessel["imo_number"]
        incoming_eta = normalize_eta(vessel["eta"])

        previous_state = get_vessel_state(vessel_name, imo_number)

        if previous_state is None:
            save_new_vessel_observation(vessel, incoming_eta)
            continue

        stored_current_eta = normalize_eta(previous_state["current_eta"])

        if incoming_eta != stored_current_eta:
            persisted_change = record_eta_change(vessel, incoming_eta)

            # A concurrent monitor could have already stored this observation.
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

    print("Monitoring complete.")
    if (len(changes) == 0):
        print("No changes since last update.")
    
    return changes
