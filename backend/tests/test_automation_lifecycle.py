"""Tests for the staged, midnight, and hourly automation lifecycle."""

from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

from PortPilot.monitoring.lifecycle import (
    initialize_current_day,
    reconcile_on_startup,
    run_hourly_update,
    run_startup_catchup,
    stage_next_day,
)
from PortPilot.monitoring.scheduler import next_daily_run, next_hourly_run
from PortPilot.agent.agent import run_monitoring_cycle


UTC = timezone.utc
SINGAPORE = ZoneInfo("Asia/Singapore")


class AutomationLifecycleTests(TestCase):
    def test_nine_pm_job_stages_tomorrow_without_running_monitoring(self):
        now = datetime(2026, 9, 5, 13, 0, tzinfo=UTC)  # 21:00 Singapore
        vessels = [{"vessel_name": "FUTURE VESSEL", "imo_number": "9000001"}]

        with (
            patch(
                "PortPilot.monitoring.lifecycle.get_vessels_due_to_arrive",
                return_value=vessels,
            ) as fetch,
            patch(
                "PortPilot.monitoring.lifecycle.stage_vessel_observations",
                return_value=1,
            ) as stage,
            patch("PortPilot.monitoring.lifecycle.monitor_vessels") as monitor,
            patch("PortPilot.monitoring.lifecycle.run_monitoring_cycle") as agent,
        ):
            result = stage_next_day(now)

        fetch.assert_called_once_with("2026-09-06")
        stage.assert_called_once_with(vessels, datetime(2026, 9, 6).date())
        monitor.assert_not_called()
        agent.assert_not_called()
        self.assertEqual(result["operational_date"], "2026-09-06")
        self.assertEqual(result["staged_vessels"], 1)

    def test_midnight_cleans_activates_then_initializes_today(self):
        now = datetime(2026, 9, 5, 16, 0, tzinfo=UTC)  # 00:00 Singapore
        call_order = []
        vessels = [{
            "vessel_name": "TODAY",
            "imo_number": "1",
            "eta": "2026-09-06T01:00:00+08:00",
        }]

        def deleted(_operating_date):
            call_order.append("delete")
            return 8

        def activated(_operating_date):
            call_order.append("activate")
            return 12

        def deactivated():
            call_order.append("deactivate_resources")
            return 17

        def monitored(_operating_date, **_kwargs):
            call_order.append("monitor")
            return [{"event": "NEW_VESSEL_DISCOVERED"}]

        def generated():
            call_order.append("generate")
            return {"berth": [{}], "pilot": [{}], "tug": [{}]}

        with (
            patch(
                "PortPilot.monitoring.lifecycle.delete_vessels_before_operational_date",
                side_effect=deleted,
            ),
            patch(
                "PortPilot.monitoring.lifecycle.activate_staged_vessels",
                side_effect=activated,
            ),
            patch(
                "PortPilot.monitoring.lifecycle.deactivate_resource_pool",
                side_effect=deactivated,
            ),
            patch(
                "PortPilot.monitoring.lifecycle.monitor_vessels",
                side_effect=monitored,
            ) as monitor,
            patch(
                "PortPilot.monitoring.lifecycle.get_vessels_due_to_arrive",
                return_value=vessels,
            ),
            patch("PortPilot.monitoring.lifecycle.generate_operations", side_effect=generated),
            patch("PortPilot.monitoring.lifecycle.run_monitoring_cycle") as agent,
        ):
            result = initialize_current_day(now)

        self.assertEqual(
            call_order,
            ["delete", "activate", "deactivate_resources", "monitor", "generate"],
        )
        monitor.assert_called_once_with(
            "2026-09-06",
            current_vessels=vessels,
            assign_operations=False,
        )
        agent.assert_not_called()
        self.assertEqual(result["operational_date"], "2026-09-06")
        self.assertEqual(result["deleted_previous_vessels"], 8)
        self.assertEqual(result["activated_staged_vessels"], 12)
        self.assertEqual(result["deactivated_previous_resources"], 17)
        self.assertEqual(result["assignments_created"]["berth"], 1)

    def test_hourly_job_runs_complete_agent_pipeline_for_today(self):
        now = datetime(2026, 9, 6, 3, 5, tzinfo=UTC)  # 11:05 Singapore
        pipeline_result = {
            "eta_change_results": [{"outcome": "rescheduled"}],
            "unconfirmed_retry_results": [],
            "raw_changes": [],
            "errors": [],
        }

        vessels = [{"vessel_name": "FUTURE", "imo_number": "1"}]
        with (
            patch(
                "PortPilot.monitoring.lifecycle._fetch_upcoming_vessels",
                return_value=vessels,
            ),
            patch(
                "PortPilot.monitoring.lifecycle.run_monitoring_cycle",
                return_value=pipeline_result,
            ) as run_cycle,
            patch("PortPilot.monitoring.lifecycle.generate_operations") as generate,
        ):
            result = run_hourly_update(now)

        run_cycle.assert_called_once_with(
            "2026-09-06",
            not_before=datetime(2026, 9, 6, 11, 5, tzinfo=SINGAPORE),
            current_vessels=vessels,
        )
        self.assertEqual(result["job"], "hourly_update")
        self.assertEqual(result["eta_change_results"][0]["outcome"], "rescheduled")
        generate.assert_not_called()

    def test_startup_reconciliation_does_not_discard_eta_changes(self):
        now = datetime(2026, 9, 6, 6, 30, tzinfo=UTC)  # 14:30 Singapore
        call_order = []

        with (
            patch(
                "PortPilot.monitoring.lifecycle.has_operational_assignments",
                side_effect=lambda _date: call_order.append("initialized") or True,
            ),
            patch(
                "PortPilot.monitoring.lifecycle.delete_vessels_before_operational_date",
                side_effect=lambda _date: call_order.append("delete") or 2,
            ),
            patch(
                "PortPilot.monitoring.lifecycle.activate_staged_vessels",
                side_effect=lambda _date: call_order.append("activate") or 0,
            ),
            patch("PortPilot.monitoring.lifecycle._fetch_upcoming_vessels", return_value=[]),
            patch(
                "PortPilot.monitoring.lifecycle.run_monitoring_cycle",
                side_effect=lambda _date, **_kwargs: call_order.append("agent") or {
                    "eta_change_results": [{"outcome": "no_action"}],
                    "unconfirmed_retry_results": [],
                    "raw_changes": [],
                    "errors": [],
                },
            ),
        ):
            result = reconcile_on_startup(now)

        self.assertEqual(call_order, ["initialized", "delete", "activate", "agent"])
        self.assertEqual(result["eta_change_results"][0]["outcome"], "no_action")

    def test_startup_after_nine_pm_only_stages_tomorrow(self):
        now = datetime(2026, 9, 5, 15, 23, tzinfo=UTC)  # 23:23 Singapore

        with (
            patch(
                "PortPilot.monitoring.lifecycle.stage_next_day",
                return_value={"job": "stage_next_day"},
            ) as stage,
            patch(
                "PortPilot.monitoring.lifecycle.has_operational_assignments",
                return_value=True,
            ),
            patch("PortPilot.monitoring.lifecycle.reconcile_on_startup") as reconcile,
        ):
            result = run_startup_catchup(now)

        stage.assert_called_once_with(
            datetime(2026, 9, 5, 23, 23, tzinfo=SINGAPORE)
        )
        reconcile.assert_not_called()
        self.assertEqual(result["job"], "stage_next_day")

    def test_scheduler_uses_singapore_daily_boundaries(self):
        before_nine = datetime(2026, 9, 5, 12, 59, tzinfo=timezone.utc)
        at_nine = datetime(2026, 9, 5, 13, 0, tzinfo=timezone.utc)

        self.assertEqual(
            next_daily_run(before_nine, 21).isoformat(),
            "2026-09-05T21:00:00+08:00",
        )
        self.assertEqual(
            next_daily_run(at_nine, 21).isoformat(),
            "2026-09-06T21:00:00+08:00",
        )

    def test_hourly_monitor_runs_at_five_minutes_past(self):
        now = datetime(2026, 9, 5, 14, 3, tzinfo=timezone.utc)

        self.assertEqual(
            next_hourly_run(now).isoformat(),
            "2026-09-05T22:05:00+08:00",
        )

    def test_hourly_cycle_recovers_existing_unconfirmed_vessels(self):
        unconfirmed = {"vessel_name": "RECOVERY VESSEL", "imo_number": "9000002"}
        recovery_result = {**unconfirmed, "outcome": "resources_allocated"}

        with (
            patch("PortPilot.agent.agent.monitor_vessels", return_value=[]),
            patch(
                "PortPilot.agent.agent.get_unconfirmed_vessel_keys",
                return_value=[unconfirmed],
            ),
            patch(
                "PortPilot.agent.agent._retry_unconfirmed_vessel",
                return_value=recovery_result,
            ) as retry,
        ):
            result = run_monitoring_cycle("2026-09-06")

        retry.assert_called_once_with(unconfirmed)
        self.assertEqual(result["unconfirmed_retry_results"], [recovery_result])


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
