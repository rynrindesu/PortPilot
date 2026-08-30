"""Tests for the first LLM-callable PortPilot tool."""

import json
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from PortPilot.agent.tools import get_vessel_schedule


class GetVesselScheduleToolTests(TestCase):
    def test_returns_complete_vessel_schedule(self):
        schedule = {
            "vessel": {
                "vessel_name": "NORTHERN GUARD",
                "imo_number": "1234567",
                "original_eta": datetime(2026, 8, 30, 10, tzinfo=timezone.utc),
                "previous_eta": None,
                "current_eta": datetime(2026, 8, 30, 11, tzinfo=timezone.utc),
                "status": "active",
            },
            "allocations": {
                "berth": {"resource_id": "B61"},
                "pilot": {"resource_id": "P06"},
                "tug": {"resource_id": "T03"},
            },
        }
        with patch("PortPilot.agent.tools.read_vessel_schedule", return_value=schedule):
            result = json.loads(
                get_vessel_schedule.invoke(
                    {"vessel_name": "NORTHERN GUARD", "imo_number": "1234567"}
                )
            )

        self.assertTrue(result["found"])
        self.assertTrue(result["valid"])
        self.assertEqual(result["allocations"]["berth"]["resource_id"], "B61")
        self.assertEqual(result["vessel"]["current_eta"], "2026-08-30T11:00:00+00:00")

    def test_returns_clear_not_found_result(self):
        with patch("PortPilot.agent.tools.read_vessel_schedule", return_value=None):
            result = json.loads(
                get_vessel_schedule.invoke(
                    {"vessel_name": "UNKNOWN", "imo_number": "0000000"}
                )
            )

        self.assertFalse(result["found"])
