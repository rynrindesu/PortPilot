from PortPilot.database.postgres import get_all_vessel_states

"""
Used to check what's currently stored in vessel_state via get_all_vessel_states()
"""
vessels = get_all_vessel_states()

for vessel in vessels:
    print("=" * 50)
    print(f"Vessel:       {vessel['vessel_name']}")
    print(f"Call Sign:    {vessel['call_sign']}")
    print(f"IMO Number:   {vessel['imo_number']}")
    print(f"Flag:         {vessel['flag']}")
    print(f"ETA:          {vessel['eta']}")
    print(f"From:         {vessel['location_from']}")
    print(f"To:           {vessel['location_to']}")
    print(f"Last Updated: {vessel['last_updated']}")

print("=" * 50)
print(f"Total vessels: {len(vessels)}")
