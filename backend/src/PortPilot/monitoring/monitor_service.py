from oceans import get_vessels_due_to_arrive

def monitor_vessels():
    vessels = get_vessels_due_to_arrive("2026-08-28")

    # Get previous state
    # Compare
    # Detect changes
    # Save new state

    return {
        "vessels": vessels,
        "changes": []
    }