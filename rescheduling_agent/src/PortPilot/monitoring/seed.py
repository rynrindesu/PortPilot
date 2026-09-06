from datetime import datetime

from PortPilot.database.postgres import save_new_vessel_observation


def seed_demo_data():
    vessel = {
        "vessel_name": "ASL 2538",
        "call_sign": "",
        "imo_number": "0",
        "flag": "SG",
        "location_from": "SEAS",
        "location_to": "APICT",
    }
    save_new_vessel_observation(vessel, datetime.fromisoformat("2026-08-28T20:00:00+00:00"), "seed")

    print("Demo vessel state seeded successfully.")


if __name__ == "__main__":
    seed_demo_data()
