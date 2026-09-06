"""Tests for OCEANS-X vessel deduplication before database processing."""

from unittest import TestCase
from unittest.mock import Mock, patch

from PortPilot.integration.oceans import get_vessels_due_to_arrive


def _api_record(name, imo, eta, location_from="A", location_to="B"):
    return {
        "vesselParticulars": {
            "vesselName": name,
            "callSign": f"CALL-{imo}",
            "imoNumber": imo,
            "flag": "SG",
        },
        "duetoArriveTime": eta,
        "locationFrom": location_from,
        "locationTo": location_to,
    }


class OceansDeduplicationTests(TestCase):
    def _fetch(self, records):
        response = Mock()
        response.json.return_value = records

        with patch(
            "PortPilot.integration.oceans.requests.get",
            return_value=response,
        ):
            vessels = get_vessels_due_to_arrive("2026-09-06")

        response.raise_for_status.assert_called_once_with()
        return vessels

    def test_conflicting_duplicates_keep_record_with_latest_eta(self):
        vessels = self._fetch([
            _api_record(
                "PALU BAY", "9983413", "2026-09-06 09:30:00",
                location_from="LATEST",
            ),
            _api_record(
                "PALU BAY", "9983413", "2026-09-06 05:00:00",
                location_from="EARLIER",
            ),
        ])

        self.assertEqual(len(vessels), 1)
        self.assertEqual(vessels[0]["eta"], "2026-09-06 09:30:00")
        self.assertEqual(vessels[0]["location_from"], "LATEST")

    def test_identical_duplicates_are_returned_once(self):
        duplicate = _api_record(
            "INSPIRE", "9760304", "2026-09-06 18:00:00"
        )

        vessels = self._fetch([duplicate, duplicate.copy()])

        self.assertEqual(len(vessels), 1)
        self.assertEqual(vessels[0]["imo_number"], "9760304")


if __name__ == "__main__":
    import unittest

    unittest.main(verbosity=2)
