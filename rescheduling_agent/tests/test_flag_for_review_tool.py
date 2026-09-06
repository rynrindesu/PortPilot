"""Tests for flag_for_review() and flag_allocation_for_review()."""

import json
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from PortPilot.agent.tools import flag_allocation_for_review, flag_for_review

T0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


class _FakeCursor:
    def __init__(self, select_responses):
        self.select_responses = list(select_responses)
        self.executed = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        kind = sql.strip().split()[0]
        self.executed.append((kind, sql, params))
        if kind == "SELECT":
            self._last_select = self.select_responses.pop(0)

    def fetchone(self):
        return self._last_select

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolledback = False

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.committed = True
        else:
            self.rolledback = True
        return False


class FlagAllocationForReviewTests(TestCase):
    def test_requires_a_reason(self):
        result = flag_allocation_for_review("berth", "TEST VESSEL A", "1111111", reason="   ")
        self.assertFalse(result["success"])
        self.assertIn("reason is required", result["message"])

    def test_rejects_unknown_resource_type(self):
        result = flag_allocation_for_review("crane", "TEST VESSEL A", "1111111", reason="test")
        self.assertFalse(result["success"])
        self.assertIn("Unknown resource_type", result["message"])

    def test_no_existing_allocation_fails_cleanly(self):
        fake_cursor = _FakeCursor([None])
        fake_connection = _FakeConnection(fake_cursor)

        with patch("PortPilot.agent.tools.get_connection", return_value=fake_connection):
            result = flag_allocation_for_review("berth", "TEST VESSEL A", "1111111", reason="test")

        self.assertFalse(result["success"])
        self.assertIn("No existing berth allocation", result["message"])
        self.assertTrue(fake_connection.rolledback)
        self.assertFalse(fake_connection.committed)

    def test_marks_pending_review_and_logs_with_unchanged_times(self):
        fake_cursor = _FakeCursor([("B01", T0, T0)])
        fake_connection = _FakeConnection(fake_cursor)

        with patch("PortPilot.agent.tools.get_connection", return_value=fake_connection):
            result = flag_allocation_for_review(
                "berth", "TEST VESSEL A", "1111111", reason="no valid option found"
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["outcome"], "human_review")
        self.assertEqual(result["resource_id"], "B01")
        self.assertTrue(fake_connection.committed)
        self.assertFalse(fake_connection.rolledback)

        kinds = [kind for kind, _, _ in fake_cursor.executed]
        self.assertEqual(kinds, ["SELECT", "UPDATE", "INSERT"])

        _, select_sql, _ = fake_cursor.executed[0]
        self.assertIn("FOR UPDATE", select_sql)  # locks this vessel's row before reading it

        _, update_sql, update_params = fake_cursor.executed[1]
        self.assertIn("pending_review", update_sql)
        self.assertEqual(update_params, ("TEST VESSEL A", "1111111"))

        insert_params = fake_cursor.executed[2][2]
        (
            vessel_name, imo_number, resource_type, resource_id,
            old_start, old_end, new_start, new_end,
            reason, decision_score, execution_mode,
        ) = insert_params
        self.assertEqual(vessel_name, "TEST VESSEL A")
        self.assertEqual(imo_number, "1111111")
        self.assertEqual(resource_type, "berth")
        self.assertEqual(resource_id, "B01")
        self.assertEqual(old_start, T0)
        self.assertEqual(new_start, T0)  # unchanged - this is an escalation, not a reschedule
        self.assertEqual(old_end, T0)
        self.assertEqual(new_end, T0)
        self.assertEqual(reason, "no valid option found")
        self.assertIsNone(decision_score)
        self.assertEqual(execution_mode, "human_review")


    def test_reason_is_stripped_before_storage(self):
        fake_cursor = _FakeCursor([("B01", T0, T0)])
        fake_connection = _FakeConnection(fake_cursor)

        with patch("PortPilot.agent.tools.get_connection", return_value=fake_connection):
            result = flag_allocation_for_review(
                "berth", "TEST VESSEL A", "1111111", reason="  needs review  "
            )

        self.assertEqual(result["reason"], "needs review")
        insert_params = fake_cursor.executed[2][2]
        self.assertEqual(insert_params[8], "needs review")


class FlagForReviewToolTests(TestCase):
    def test_invoke_returns_json_success(self):
        fake_cursor = _FakeCursor([("P01", T0, T0)])
        fake_connection = _FakeConnection(fake_cursor)

        with patch("PortPilot.agent.tools.get_connection", return_value=fake_connection):
            raw_result = flag_for_review.invoke({
                "resource_type": "pilot",
                "vessel_name": "TEST VESSEL A",
                "imo_number": "1111111",
                "reason": "no valid option found",
            })

        result = json.loads(raw_result)
        self.assertTrue(result["success"])
        self.assertEqual(result["outcome"], "human_review")
