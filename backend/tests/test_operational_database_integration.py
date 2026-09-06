"""Integration test for the live vessel feed and frozen operations schedule.

Run with a configured SUPABASE_DB_URL/SUPABASE_DB_PASSWORD:

    cd backend && pytest tests/test_operational_database_integration.py

All writes are rolled back.  The test therefore exercises the real database
relationships without leaving demo data behind.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from PortPilot.database.postgres import get_connection


def test_live_eta_change_does_not_overwrite_frozen_operational_schedule():
    """A monitoring update may change vessel_state only, never operations data."""
    suffix = uuid4().hex[:10]
    vessel_name = f"TEST VESSEL {suffix}"
    imo_number = f"9{suffix[:6]}"
    baseline_eta = datetime(2026, 8, 28, 10, tzinfo=timezone.utc)
    observed_eta = baseline_eta + timedelta(hours=4)
    pilot_start = baseline_eta - timedelta(minutes=30)
    pilot_end = baseline_eta + timedelta(minutes=30)
    tug_start = baseline_eta - timedelta(minutes=15)
    tug_end = baseline_eta + timedelta(hours=1)
    berth_start = baseline_eta + timedelta(minutes=30)
    berth_end = baseline_eta + timedelta(hours=8)

    with get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                # First observation creates both the live record and its one-time
                # baseline operational plan.
                cursor.execute(
                    """
                    INSERT INTO vessel_state
                        (vessel_name, imo_number, original_eta, current_eta,
                         call_sign, flag, location_from, location_to,
                         operational_date, lifecycle_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
                    """,
                    (
                        vessel_name,
                        imo_number,
                        baseline_eta,
                        baseline_eta,
                        "TST1",
                        "SG",
                        "TEST",
                        "SGSIN",
                        baseline_eta.date(),
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO operations_vessels (vessel_name, imo_number, current_eta)
                    VALUES (%s, %s, %s)
                    """,
                    (vessel_name, imo_number, baseline_eta),
                )
                cursor.execute(
                    """
                    INSERT INTO pilot_assignments
                        (vessel_name, imo_number, pilot_id, start_time, end_time, status)
                    VALUES (%s, %s, %s, %s, %s, 'confirmed')
                    """,
                    (vessel_name, imo_number, f"P{suffix[:4]}", pilot_start, pilot_end),
                )
                cursor.execute(
                    """
                    INSERT INTO tug_assignments
                        (vessel_name, imo_number, tug_id, start_time, end_time, status)
                    VALUES (%s, %s, %s, %s, %s, 'confirmed')
                    """,
                    (vessel_name, imo_number, f"T{suffix[:4]}", tug_start, tug_end),
                )
                cursor.execute(
                    """
                    INSERT INTO berth_allocations
                        (vessel_name, imo_number, berth_id, start_time, end_time, status)
                    VALUES (%s, %s, %s, %s, %s, 'confirmed')
                    """,
                    (vessel_name, imo_number, f"B{suffix[:4]}", berth_start, berth_end),
                )

                # This represents the next OCEANS-X poll.  It must deliberately
                # not update operations_vessels or any resource assignment.
                cursor.execute(
                    """
                    UPDATE vessel_state
                    SET previous_eta = current_eta, current_eta = %s, last_updated = NOW()
                    WHERE vessel_name = %s AND imo_number = %s
                    """,
                    (observed_eta, vessel_name, imo_number),
                )

                cursor.execute(
                    """
                    SELECT original_eta, previous_eta, current_eta FROM vessel_state
                    WHERE vessel_name = %s AND imo_number = %s
                    """,
                    (vessel_name, imo_number),
                )
                original_eta, previous_eta, current_eta = cursor.fetchone()
                assert original_eta == baseline_eta
                assert previous_eta == baseline_eta
                assert current_eta == observed_eta

                cursor.execute(
                    """
                    SELECT current_eta FROM operations_vessels
                    WHERE vessel_name = %s AND imo_number = %s
                    """,
                    (vessel_name, imo_number),
                )
                assert cursor.fetchone()[0] == baseline_eta

                for table, expected_start, expected_end in (
                    ("pilot_assignments", pilot_start, pilot_end),
                    ("tug_assignments", tug_start, tug_end),
                    ("berth_allocations", berth_start, berth_end),
                ):
                    cursor.execute(
                        f"""SELECT start_time, end_time, status FROM {table}
                        WHERE vessel_name = %s AND imo_number = %s""",
                        (vessel_name, imo_number),
                    )
                    start_time, end_time, status = cursor.fetchone()
                    assert (start_time, end_time, status) == (
                        expected_start,
                        expected_end,
                        "confirmed",
                    )

                # A later agent action records a complete before/after audit entry.
                new_start = pilot_start + timedelta(hours=4)
                new_end = pilot_end + timedelta(hours=4)
                cursor.execute(
                    """
                    UPDATE pilot_assignments
                    SET start_time = %s, end_time = %s, status = 'pending_review'
                    WHERE vessel_name = %s AND imo_number = %s
                    """,
                    (new_start, new_end, vessel_name, imo_number),
                )
                cursor.execute(
                    """
                    INSERT INTO schedule_changes
                        (vessel_name, imo_number, resource_type, resource_id,
                         old_start_time, old_end_time, new_start_time, new_end_time,
                         reason, changed_by)
                    VALUES (%s, %s, 'pilot', %s, %s, %s, %s, %s, %s, 'agent')
                    """,
                    (
                        vessel_name, imo_number, f"P{suffix[:4]}", pilot_start,
                        pilot_end, new_start, new_end,
                        "Observed ETA changed by four hours; pilot slot moved for review.",
                    ),
                )
                cursor.execute(
                    """
                    SELECT old_start_time, old_end_time, new_start_time, new_end_time,
                           changed_by
                    FROM schedule_changes
                    WHERE vessel_name = %s AND imo_number = %s AND resource_type = 'pilot'
                    """,
                    (vessel_name, imo_number),
                )
                assert cursor.fetchone() == (pilot_start, pilot_end, new_start, new_end, "agent")
        finally:
            # Return the pooled connection without retaining integration-test data.
            connection.rollback()
