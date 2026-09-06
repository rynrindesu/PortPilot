"""Unit tests for ETA-state transitions in the monitoring service."""

from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from PortPilot.monitoring.monitor_service import monitor_vessels


VESSEL = {
    "vessel_name": "TEST VESSEL",
    "imo_number": "1234567",
    "eta": "2026-08-30T12:00:00Z",
    "call_sign": None,
    "flag": "SG",
    "location_from": "SG",
    "location_to": "SGSIN",
}


class MonitoringEtaStateTests(TestCase):
    def setUp(self):
        allocation_keys_patcher = patch(
            "PortPilot.monitoring.monitor_service.get_allocation_keys_by_type",
            return_value={"berth": set(), "pilot": set(), "tug": set()},
        )
        assignment_patcher = patch(
            "PortPilot.monitoring.monitor_service.assign_initial_operations",
            return_value={},
        )
        allocation_keys_patcher.start()
        assignment_patcher.start()
        self.addCleanup(allocation_keys_patcher.stop)
        self.addCleanup(assignment_patcher.stop)

    def test_scheduled_poll_skips_vessels_with_passed_eta(self):
        past_vessel = {**VESSEL, "vessel_name": "PAST", "eta": "2026-08-30T10:00:00Z"}
        future_vessel = {
            **VESSEL,
            "vessel_name": "FUTURE",
            "eta": "2026-08-30T12:00:00Z",
        }

        with (
            patch(
                "PortPilot.monitoring.monitor_service.get_vessels_due_to_arrive",
                return_value=[past_vessel, future_vessel],
            ),
            patch(
                "PortPilot.monitoring.monitor_service.get_vessel_state",
                return_value=None,
            ) as get_state,
            patch(
                "PortPilot.monitoring.monitor_service.save_new_vessel_observation",
                return_value=False,
            ),
        ):
            monitor_vessels(
                "2026-08-30",
                not_before=datetime(2026, 8, 30, 11, 0, tzinfo=timezone.utc),
            )

        get_state.assert_called_once_with("FUTURE", "1234567")

    def test_staged_vessel_is_not_assigned_before_activation(self):
        with (
            patch(
                "PortPilot.monitoring.monitor_service.get_vessels_due_to_arrive",
                return_value=[VESSEL],
            ),
            patch("PortPilot.monitoring.monitor_service.get_vessel_state", return_value=None),
            patch(
                "PortPilot.monitoring.monitor_service.save_new_vessel_observation",
                return_value=False,
            ),
            patch(
                "PortPilot.monitoring.monitor_service.assign_initial_operations"
            ) as assign,
        ):
            changes = monitor_vessels("2026-08-31")

        self.assertEqual(changes, [])
        assign.assert_not_called()

    def test_new_vessel_initializes_original_and_current_eta(self):
        with (
            patch("PortPilot.monitoring.monitor_service.get_vessels_due_to_arrive", return_value=[VESSEL]),
            patch("PortPilot.monitoring.monitor_service.get_vessel_state", return_value=None),
            patch("PortPilot.monitoring.monitor_service.save_new_vessel_observation") as save_new,
        ):
            changes = monitor_vessels("2026-08-30")

        self.assertEqual(
            changes,
            [{
                "event": "NEW_VESSEL_DISCOVERED",
                "vessel_name": "TEST VESSEL",
                "imo_number": "1234567",
                "eta": "2026-08-30T12:00:00+00:00",
                "assigned": {},
                "assignment_error": None,
            }],
        )
        save_new.assert_called_once_with(
            VESSEL,
            datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
        )

    def test_unchanged_eta_refreshes_metadata_without_changing_eta_state(self):
        state = {"current_eta": datetime(2026, 8, 30, 12, tzinfo=timezone.utc)}
        with (
            patch("PortPilot.monitoring.monitor_service.get_vessels_due_to_arrive", return_value=[VESSEL]),
            patch("PortPilot.monitoring.monitor_service.get_vessel_state", return_value=state),
            patch("PortPilot.monitoring.monitor_service.refresh_vessel_observation") as refresh,
            patch("PortPilot.monitoring.monitor_service.record_eta_change") as record_change,
        ):
            changes = monitor_vessels("2026-08-30")

        self.assertEqual(changes, [])
        refresh.assert_called_once_with(VESSEL)
        record_change.assert_not_called()

    def test_changed_eta_records_transition_and_emits_event(self):
        old_eta = datetime(2026, 8, 30, 10, tzinfo=timezone.utc)
        new_eta = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
        state = {"current_eta": old_eta}
        persisted_change = {"previous_eta": old_eta, "current_eta": new_eta}

        with (
            patch("PortPilot.monitoring.monitor_service.get_vessels_due_to_arrive", return_value=[VESSEL]),
            patch("PortPilot.monitoring.monitor_service.get_vessel_state", return_value=state),
            patch("PortPilot.monitoring.monitor_service.record_eta_change", return_value=persisted_change) as record_change,
        ):
            changes = monitor_vessels("2026-08-30")

        record_change.assert_called_once_with(VESSEL, new_eta)
        self.assertEqual(
            changes,
            [
                {
                    "event": "ETA_CHANGED",
                    "vessel_name": "TEST VESSEL",
                    "imo_number": "1234567",
                    "previous_eta": "2026-08-30T10:00:00+00:00",
                    "new_eta": "2026-08-30T12:00:00+00:00",
                }
            ],
        )
