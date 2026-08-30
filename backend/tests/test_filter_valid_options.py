from datetime import datetime, timezone
from pprint import pprint

from PortPilot.agent.scheduling_rules import filter_valid_options

"""
Runs filter_valid_options() against a realistic sample of
generate_schedule_options()'s output for one disrupted vessel
(MAO GANG GUANG ZHOU, IMO 9981348, new ETA 2026-08-30 23:30 UTC):

  - "retain_current_allocation" -> the vessel's existing, unmoved booking
  - "shift_same_resources"      -> same resources, shifted to the new ETA
  - "reallocate_one_vessel_1"   -> moves the vessel to different resources,
    displacing NORTHERN MONUMENT's berth, with a replacement berth
    allocation for NORTHERN MONUMENT already included in the candidate

This checks against the live database (read-only), so results reflect
whatever is actually seeded there - a candidate can come back invalid if
its assumed resources are occupied by a real, non-disrupted vessel that
wasn't accounted for when the sample was written.
"""

options = [
    {
        "option_id": "retain_current_allocation",
        "strategy": "retain_current_allocation",
        "target_eta": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
        "affected_vessels": [
            {"vessel_name": "MAO GANG GUANG ZHOU", "imo_number": "9981348"}
        ],
        "changes": [
            {
                "vessel_name": "MAO GANG GUANG ZHOU",
                "imo_number": "9981348",
                "allocations": {
                    "berth": {
                        "resource_id": "B25",
                        "start_time": datetime(2026, 8, 30, 22, 30, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 31, 3, 54, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                    "pilot": {
                        "resource_id": "P16",
                        "start_time": datetime(2026, 8, 30, 21, 43, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 30, 22, 30, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                    "tug": {
                        "resource_id": "T13",
                        "start_time": datetime(2026, 8, 30, 22, 30, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 30, 23, 18, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                },
            }
        ],
        "resource_conflicts": [],
    },
    {
        "option_id": "shift_same_resources",
        "strategy": "shift_same_resources",
        "target_eta": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
        "affected_vessels": [
            {"vessel_name": "MAO GANG GUANG ZHOU", "imo_number": "9981348"}
        ],
        "changes": [
            {
                "vessel_name": "MAO GANG GUANG ZHOU",
                "imo_number": "9981348",
                "allocations": {
                    "berth": {
                        "resource_id": "B25",
                        "start_time": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 31, 4, 54, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                    "pilot": {
                        "resource_id": "P16",
                        "start_time": datetime(2026, 8, 30, 22, 43, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                    "tug": {
                        "resource_id": "T13",
                        "start_time": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 31, 0, 18, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                },
            }
        ],
        "resource_conflicts": [],
    },
    {
        "option_id": "reallocate_one_vessel_1",
        "strategy": "reallocate_one_vessel",
        "target_eta": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
        "affected_vessels": [
            {"vessel_name": "MAO GANG GUANG ZHOU", "imo_number": "9981348"},
            {"vessel_name": "NORTHERN MONUMENT", "imo_number": "9252577"},
        ],
        "changes": [
            {
                "vessel_name": "MAO GANG GUANG ZHOU",
                "imo_number": "9981348",
                "allocations": {
                    "berth": {
                        "resource_id": "B15",
                        "start_time": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 31, 4, 54, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                    "pilot": {
                        "resource_id": "P01",
                        "start_time": datetime(2026, 8, 30, 22, 43, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                    "tug": {
                        "resource_id": "T01",
                        "start_time": datetime(2026, 8, 30, 23, 30, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 31, 0, 18, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                },
            },
            {
                "vessel_name": "NORTHERN MONUMENT",
                "imo_number": "9252577",
                "allocations": {
                    "berth": {
                        "resource_id": "B25",
                        "start_time": datetime(2026, 8, 30, 22, 45, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 31, 6, 37, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                    "pilot": {
                        "resource_id": "P02",
                        "start_time": datetime(2026, 8, 30, 21, 33, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 30, 22, 45, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                    "tug": {
                        "resource_id": "T13",
                        "start_time": datetime(2026, 8, 30, 22, 45, tzinfo=timezone.utc),
                        "end_time": datetime(2026, 8, 30, 23, 25, tzinfo=timezone.utc),
                        "buffer_minutes": 15,
                    },
                },
            },
        ],
        "resource_conflicts": [
            {
                "resource_type": "berth",
                "resource_id": "B15",
                "vessel_name": "NORTHERN MONUMENT",
                "imo_number": "9252577",
            }
        ],
    },
]

valid, invalid = filter_valid_options(options)

print("valid:")
pprint(valid)
print()
print("invalid:")
pprint(invalid)
