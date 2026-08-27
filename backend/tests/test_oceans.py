from portpilot.integration.oceans import get_vessels_due_to_arrive

"""
Used to test the connection to the OCEAN-X API and print the output
"""
vessels = get_vessels_due_to_arrive("2026-08-28")

for vessel in vessels:
    print("=" * 50)
    print(f"Vessel:       {vessel['vessel_name']}")
    print(f"Call Sign:    {vessel['call_sign']}")
    print(f"IMO Number:   {vessel['imo_number']}")
    print(f"Flag:         {vessel['flag']}")
    print(f"ETA:          {vessel['eta']}")
    print(f"From:         {vessel['location_from']}")
    print(f"To:           {vessel['location_to']}")

print("=" * 50)
print(f"Total vessels: {len(vessels)}")