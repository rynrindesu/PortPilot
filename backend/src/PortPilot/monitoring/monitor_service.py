from PortPilot.integration.oceans import get_vessels_due_to_arrive

from PortPilot.database.postgres import (
    get_vessel_state,
    save_vessel_state,
)


def monitor_vessels(date):

    print("Fetching OCEANS-X data...")
    current_vessels = get_vessels_due_to_arrive(date)
    print(f"Received {len(current_vessels)} vessels.")

    changes = []

    for vessel in current_vessels:

        print(f"Processing {vessel['vessel_name']}...")

        vessel_name = vessel["vessel_name"]
        current_eta = vessel["eta"]

        previous_state = get_vessel_state(vessel_name)

        if previous_state is not None:
            previous_eta = previous_state["eta"]

            if previous_eta != current_eta:
                changes.append({
                    "event": "ETA_CHANGED",
                    "vessel_name": vessel_name,
                    "previous_eta": str(previous_eta),
                    "new_eta": current_eta,
                })

        save_vessel_state(vessel)

    print("Monitoring complete.")
    if (len(changes) == 0):
        print("No changes since last update.")
    
    return changes