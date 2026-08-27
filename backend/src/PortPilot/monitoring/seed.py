from portpilot.database.postgres import save_vessel_state


def seed_demo_data():
    save_vessel_state({
        "vessel_name": "ASL 2538",
        "eta": "2026-08-28T20:00:00+00:00",
        "call_sign": "",
        "imo_number": "0",
        "flag": "SG",
        "location_from": "SEAS",
        "location_to": "APICT",
    })

    print("Demo vessel state seeded successfully.")


if __name__ == "__main__":
    seed_demo_data()