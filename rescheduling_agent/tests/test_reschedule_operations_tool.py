"""Tests for reschedule_operations() and apply_schedule_option()."""

import json
from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from PortPilot.agent.graph import AgentState
from PortPilot.agent.tools import apply_schedule_option, reschedule_operations

T0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


def _option(option_id, changes, rank=1):
    return {
        "option_id": option_id,
        "strategy": "alternative_resources",
        "target_eta": T0,
        "affected_vessels": [
            {"vessel_name": c["vessel_name"], "imo_number": c["imo_number"]} for c in changes
        ],
        "changes": changes,
        "resource_conflicts": [],
        "rank": rank,
        "scores": {
            "affected_vessel_count": 1, "total_schedule_shift": 0.0,
            "repeat_changes": 0, "resource_utilisation": 0.0,
        },
    }


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
        return False  # never suppress, matches real psycopg behaviour


class ApplyScheduleOptionTests(TestCase):
    def test_requires_a_reason(self):
        option = _option("opt_1", [])
        result = apply_schedule_option(option, reason="   ")
        self.assertFalse(result["success"])
        self.assertIn("reason is required", result["message"])

    def test_rejects_option_no_longer_valid(self):
        option = _option("opt_1", [])
        with patch(
            "PortPilot.agent.tools.filter_valid_options",
            return_value=([], [{**option, "invalid_reason": "APRIL has FCFS priority"}]),
        ):
            result = apply_schedule_option(option, reason="test")

        self.assertFalse(result["success"])
        self.assertIn("no longer valid", result["message"])

    def test_applies_every_change_in_one_transaction(self):
        changes = [
            {
                "vessel_name": "TEST VESSEL A", "imo_number": "1111111",
                "allocations": {
                    "berth": {"resource_id": "B01", "start_time": T0, "end_time": T0, "buffer_minutes": 15},
                    "tug": {"resource_id": "T01", "start_time": T0, "end_time": T0, "buffer_minutes": 15},
                },
            },
            {
                "vessel_name": "TEST VESSEL B", "imo_number": "2222222",
                "allocations": {
                    "pilot": {"resource_id": "P01", "start_time": T0, "end_time": T0, "buffer_minutes": 15},
                },
            },
        ]
        option = _option("opt_1", changes)
        # Allocations are processed sorted by (resource_type, resource_id):
        # berth, pilot, tug. Each one locks its resource row, rechecks for
        # conflicts (mocked below, not via the cursor), then reads the old
        # values, updates, and logs.
        fake_cursor = _FakeCursor([
            ("berth",), ("B00", T0, T0, 15, "confirmed"),
            ("pilot",), ("P00", T0, T0, 15, "confirmed"),
            ("tug",), ("T00", T0, T0, 15, "confirmed"),
        ])
        fake_connection = _FakeConnection(fake_cursor)

        with patch("PortPilot.agent.tools.filter_valid_options", return_value=([option], [])), \
             patch("PortPilot.agent.tools.get_connection", return_value=fake_connection), \
             patch("PortPilot.agent.tools.find_resource_conflicts", return_value=[]):
            result = apply_schedule_option(option, reason="rebalance after eta change")

        self.assertTrue(result["success"])
        self.assertEqual(len(result["changes_applied"]), 3)
        self.assertTrue(fake_connection.committed)
        self.assertFalse(fake_connection.rolledback)
        kinds = [kind for kind, _, _ in fake_cursor.executed]
        self.assertEqual(kinds, ["SELECT", "SELECT", "UPDATE", "INSERT"] * 3)

    def test_failure_partway_through_rolls_back_everything(self):
        changes = [
            {
                "vessel_name": "TEST VESSEL A", "imo_number": "1111111",
                "allocations": {
                    "berth": {"resource_id": "B01", "start_time": T0, "end_time": T0, "buffer_minutes": 15},
                    "tug": {"resource_id": "T01", "start_time": T0, "end_time": T0, "buffer_minutes": 15},
                },
            },
        ]
        option = _option("opt_1", changes)
        # Berth locks and applies fine; tug's resource lock succeeds but its
        # old-value row is missing - should abort and roll back, not leave
        # the berth UPDATE applied on its own.
        fake_cursor = _FakeCursor([
            ("berth",), ("B00", T0, T0, 15, "confirmed"), ("tug",), None,
        ])
        fake_connection = _FakeConnection(fake_cursor)

        with patch("PortPilot.agent.tools.filter_valid_options", return_value=([option], [])), \
             patch("PortPilot.agent.tools.get_connection", return_value=fake_connection), \
             patch("PortPilot.agent.tools.find_resource_conflicts", return_value=[]):
            result = apply_schedule_option(option, reason="rebalance")

        self.assertFalse(result["success"])
        self.assertIn("Failed to apply option", result["message"])
        self.assertFalse(fake_connection.committed)
        self.assertTrue(fake_connection.rolledback)

    def test_processes_resources_in_sorted_order_regardless_of_input_order(self):
        """Two applies touching an overlapping resource set in different
        orders must still process them in the same canonical order, or they
        could deadlock against each other."""
        changes = [{
            "vessel_name": "TEST VESSEL A", "imo_number": "1111111",
            "allocations": {
                # Listed tug-then-berth here, the opposite of alphabetical -
                # processing order must still come out berth-then-tug.
                "tug": {"resource_id": "T01", "start_time": T0, "end_time": T0, "buffer_minutes": 15},
                "berth": {"resource_id": "B01", "start_time": T0, "end_time": T0, "buffer_minutes": 15},
            },
        }]
        option = _option("opt_1", changes)
        fake_cursor = _FakeCursor([
            ("berth",), ("B00", T0, T0, 15, "confirmed"),
            ("tug",), ("T00", T0, T0, 15, "confirmed"),
        ])
        fake_connection = _FakeConnection(fake_cursor)

        with patch("PortPilot.agent.tools.filter_valid_options", return_value=([option], [])), \
             patch("PortPilot.agent.tools.get_connection", return_value=fake_connection), \
             patch("PortPilot.agent.tools.find_resource_conflicts", return_value=[]):
            result = apply_schedule_option(option, reason="test")

        self.assertTrue(result["success"])
        self.assertEqual(
            [change["resource_type"] for change in result["changes_applied"]],
            ["berth", "tug"],
        )

    def test_conflict_found_after_lock_aborts_before_any_write(self):
        """Demonstrates the concurrency protection directly: if another
        operation committed a conflicting booking on the target resource
        after filter_valid_options() validated this option but before we
        acquired the resource lock, the post-lock recheck catches it and the
        whole option is rejected - this is exactly what happens when two
        concurrent reschedule_operations calls race for the same
        pilot/tug/berth. Whichever one's lock loses the race sees this
        failure; the other one's booking stands, and no double-booking is
        ever written."""
        option = _option("opt_1", [{
            "vessel_name": "TEST VESSEL A", "imo_number": "1111111",
            "allocations": {"berth": {"resource_id": "B01", "start_time": T0, "end_time": T0, "buffer_minutes": 15}},
        }])
        # Only the resource lock should ever be reached - no old-value
        # SELECT, no UPDATE, no INSERT, because the conflict is caught first.
        fake_cursor = _FakeCursor([("berth",)])
        fake_connection = _FakeConnection(fake_cursor)
        concurrent_booking = [{
            "assignment_id": 1, "vessel_name": "OTHER VESSEL", "imo_number": "9999999",
            "resource_id": "B01", "start_time": T0, "end_time": T0,
            "buffer_minutes": 15, "status": "confirmed",
        }]

        with patch("PortPilot.agent.tools.filter_valid_options", return_value=([option], [])), \
             patch("PortPilot.agent.tools.get_connection", return_value=fake_connection), \
             patch("PortPilot.agent.tools.find_resource_conflicts", return_value=concurrent_booking):
            result = apply_schedule_option(option, reason="test")

        self.assertFalse(result["success"])
        self.assertIn("booked by another operation", result["message"])
        self.assertIn("OTHER VESSEL", result["message"])
        self.assertTrue(fake_connection.rolledback)
        self.assertFalse(fake_connection.committed)
        kinds = [kind for kind, _, _ in fake_cursor.executed]
        self.assertEqual(kinds, ["SELECT"])  # only the resource lock - no write attempted

    def test_insert_receives_correct_audit_data(self):
        changes = [{
            "vessel_name": "TEST VESSEL A", "imo_number": "1111111",
            "allocations": {
                "berth": {
                    "resource_id": "B01",
                    "start_time": T0 + timedelta(hours=1),
                    "end_time": T0 + timedelta(hours=2),
                    "buffer_minutes": 15,
                },
            },
        }]
        option = _option("opt_1", changes, rank=2)
        # Old row on record: different resource, different (shorter) window.
        fake_cursor = _FakeCursor([
            ("berth",), ("B00", T0, T0 + timedelta(minutes=30), 20, "confirmed"),
        ])
        fake_connection = _FakeConnection(fake_cursor)

        with patch("PortPilot.agent.tools.filter_valid_options", return_value=([option], [])), \
             patch("PortPilot.agent.tools.get_connection", return_value=fake_connection), \
             patch("PortPilot.agent.tools.find_resource_conflicts", return_value=[]):
            result = apply_schedule_option(
                option, reason="displaced by MAZU 06's reschedule", execution_mode="autonomous"
            )

        self.assertTrue(result["success"])
        insert_calls = [params for kind, _, params in fake_cursor.executed if kind == "INSERT"]
        self.assertEqual(len(insert_calls), 1)
        (
            vessel_name, imo_number, resource_type, resource_id,
            old_start, old_end, new_start, new_end,
            reason, decision_score, execution_mode,
        ) = insert_calls[0]

        self.assertEqual(vessel_name, "TEST VESSEL A")
        self.assertEqual(imo_number, "1111111")
        self.assertEqual(resource_type, "berth")
        self.assertEqual(resource_id, "B01")
        self.assertEqual(old_start, T0)
        self.assertEqual(old_end, T0 + timedelta(minutes=30))
        self.assertEqual(new_start, T0 + timedelta(hours=1))
        self.assertEqual(new_end, T0 + timedelta(hours=2))
        self.assertEqual(reason, "displaced by MAZU 06's reschedule")
        self.assertEqual(decision_score, 2)  # the option's rank
        self.assertEqual(execution_mode, "autonomous")

    def test_reads_old_values_with_row_lock(self):
        """The old-values SELECT must lock this vessel's allocation row (the
        same row flag_allocation_for_review() locks), so the two write paths
        can't interleave and produce a stale audit entry or clobber each
        other's write."""
        option = _option("opt_1", [{
            "vessel_name": "TEST VESSEL A", "imo_number": "1111111",
            "allocations": {"berth": {"resource_id": "B01", "start_time": T0, "end_time": T0, "buffer_minutes": 15}},
        }])
        fake_cursor = _FakeCursor([("berth",), ("B00", T0, T0, 15, "confirmed")])
        fake_connection = _FakeConnection(fake_cursor)

        with patch("PortPilot.agent.tools.filter_valid_options", return_value=([option], [])), \
             patch("PortPilot.agent.tools.get_connection", return_value=fake_connection), \
             patch("PortPilot.agent.tools.find_resource_conflicts", return_value=[]):
            apply_schedule_option(option, reason="test")

        select_sqls = [sql for kind, sql, _ in fake_cursor.executed if kind == "SELECT"]
        self.assertEqual(len(select_sqls), 2)
        self.assertIn("FROM resources", select_sqls[0])
        self.assertIn("FOR UPDATE", select_sqls[0])  # locks the resources-table row for the new resource_id
        self.assertNotIn("FROM resources", select_sqls[1])
        self.assertIn("FOR UPDATE", select_sqls[1])  # locks this vessel's own allocation row

    def test_reason_is_stripped_before_storage(self):
        changes = [{
            "vessel_name": "TEST VESSEL A", "imo_number": "1111111",
            "allocations": {"berth": {"resource_id": "B01", "start_time": T0, "end_time": T0, "buffer_minutes": 15}},
        }]
        option = _option("opt_1", changes)
        fake_cursor = _FakeCursor([("berth",), ("B00", T0, T0, 15, "confirmed")])
        fake_connection = _FakeConnection(fake_cursor)

        with patch("PortPilot.agent.tools.filter_valid_options", return_value=([option], [])), \
             patch("PortPilot.agent.tools.get_connection", return_value=fake_connection), \
             patch("PortPilot.agent.tools.find_resource_conflicts", return_value=[]):
            apply_schedule_option(option, reason="  needs review  ")

        insert_params = [params for kind, _, params in fake_cursor.executed if kind == "INSERT"][0]
        self.assertEqual(insert_params[8], "needs review")

    def test_applies_revalidated_changes_not_the_stale_original(self):
        """If filter_valid_options() returns a modified option - e.g. with an
        added replacement allocation for a vessel displaced during
        revalidation - apply_schedule_option() must write THAT version, not
        the original option that was passed in."""
        original_changes = [{
            "vessel_name": "TEST VESSEL A", "imo_number": "1111111",
            "allocations": {"berth": {"resource_id": "B01", "start_time": T0, "end_time": T0, "buffer_minutes": 15}},
        }]
        original_option = _option("opt_1", original_changes)

        # filter_valid_options() decided vessel A's move displaces vessel C
        # from its pilot slot and found it a replacement - this change is
        # NOT present in original_option at all.
        revalidated_changes = original_changes + [{
            "vessel_name": "TEST VESSEL C", "imo_number": "3333333",
            "allocations": {"pilot": {"resource_id": "P09", "start_time": T0, "end_time": T0, "buffer_minutes": 15}},
        }]
        revalidated_option = {**original_option, "changes": revalidated_changes}

        fake_cursor = _FakeCursor([
            ("berth",), ("B00", T0, T0, 15, "confirmed"),
            ("pilot",), ("P00", T0, T0, 15, "confirmed"),
        ])
        fake_connection = _FakeConnection(fake_cursor)

        with patch("PortPilot.agent.tools.filter_valid_options", return_value=([revalidated_option], [])), \
             patch("PortPilot.agent.tools.get_connection", return_value=fake_connection), \
             patch("PortPilot.agent.tools.find_resource_conflicts", return_value=[]):
            result = apply_schedule_option(original_option, reason="test")

        self.assertTrue(result["success"])
        # Both vessel A's own change AND vessel C's replacement must have
        # been applied - proving the revalidated changes were used, not
        # original_option's stale single-vessel list.
        applied_vessels = {(c["vessel_name"], c["imo_number"]) for c in result["changes_applied"]}
        self.assertEqual(applied_vessels, {("TEST VESSEL A", "1111111"), ("TEST VESSEL C", "3333333")})


class RescheduleOperationsToolTests(TestCase):
    """The tool resolves model selections against authoritative graph state."""

    def test_tool_schema_exposes_only_option_id_and_reason(self):
        properties = reschedule_operations.tool_call_schema.model_json_schema()["properties"]

        self.assertEqual(set(properties), {"option_id", "reason"})

    def test_compiled_tool_node_injects_ranked_option_state(self):
        ranked_option = _option("alt_1", [])
        builder = StateGraph(AgentState)
        builder.add_node("tools", ToolNode([reschedule_operations]))
        builder.set_entry_point("tools")
        builder.add_edge("tools", END)
        graph = builder.compile()

        with patch(
            "PortPilot.agent.tools.apply_schedule_option",
            return_value={"success": True, "option_id": "alt_1", "changes_applied": []},
        ) as mock_apply:
            result_state = graph.invoke({
                "messages": [AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "reschedule_operations",
                        "args": {
                            "option_id": "alt_1",
                            "reason": "picked top option",
                        },
                        "id": "selection-1",
                        "type": "tool_call",
                    }],
                )],
                "ranked_result": {"options": [ranked_option]},
            })

        result = json.loads(result_state["messages"][-1].content)
        self.assertTrue(result["success"])
        self.assertEqual(mock_apply.call_args[0][0], ranked_option)

    def test_resolves_option_from_state_parses_iso_strings_and_applies(self):
        ranked_option = json.loads(json.dumps({
            "option_id": "alt_1",
            "target_eta": T0.isoformat(),
            "changes": [{
                "vessel_name": "TEST VESSEL A", "imo_number": "1111111",
                "allocations": {
                    "berth": {
                        "resource_id": "B01",
                        "start_time": T0.isoformat(), "end_time": T0.isoformat(),
                        "buffer_minutes": 15,
                    },
                },
            }],
        }))

        with patch(
            "PortPilot.agent.tools.apply_schedule_option",
            return_value={"success": True, "option_id": "alt_1", "changes_applied": []},
        ) as mock_apply:
            raw_result = reschedule_operations.func(
                option_id="alt_1",
                reason="picked top option",
                state={"ranked_result": {"options": [ranked_option]}},
            )

        result = json.loads(raw_result)
        self.assertTrue(result["success"])
        applied_option = mock_apply.call_args[0][0]
        self.assertEqual(applied_option["target_eta"], T0)
        self.assertEqual(
            applied_option["changes"][0]["allocations"]["berth"]["start_time"], T0
        )

    def test_malformed_datetime_fails_cleanly(self):
        bad_option = {"option_id": "alt_1", "target_eta": "not-a-real-date", "changes": []}
        raw_result = reschedule_operations.func(
            option_id="alt_1",
            reason="test",
            state={"ranked_result": {"options": [bad_option]}},
        )
        result = json.loads(raw_result)
        self.assertFalse(result["success"])
        self.assertIn("Malformed option", result["message"])

    def test_unknown_option_id_fails_without_applying(self):
        with patch("PortPilot.agent.tools.apply_schedule_option") as mock_apply:
            raw_result = reschedule_operations.func(
                option_id="missing_option",
                reason="test",
                state={"ranked_result": {"options": []}},
            )

        result = json.loads(raw_result)
        self.assertFalse(result["success"])
        self.assertIn("not available", result["message"])
        mock_apply.assert_not_called()
