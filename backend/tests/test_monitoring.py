from portpilot.monitoring.monitor_service import monitor_vessels


def test_monitoring():
    changes = monitor_vessels("2026-08-28")

    print("\nDetected changes:")

    if not changes:
        print("No changes detected.")
        return

    for change in changes:
        print(change)


if __name__ == "__main__":
    test_monitoring()