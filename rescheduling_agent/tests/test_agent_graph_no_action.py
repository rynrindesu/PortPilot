"""Regression tests for the rescheduling graph's no-action outcome."""

from datetime import datetime, timezone
from unittest import TestCase

from langchain_core.messages import AIMessage

from PortPilot.agent.graph import finalize_node, validate_tool_call_node


REVISED_ETA = datetime(2026, 9, 5, 20, 36, tzinfo=timezone.utc)


def _retain_option():
    return {
        "option_id": "retain_current_allocation",
        "strategy": "retain_current_allocation",
        "target_eta": REVISED_ETA,
        "affected_vessels": [],
        "changes": [],
        "resource_conflicts": [],
        "rank": 1,
        "scores": {},
    }


class NoActionGraphTests(TestCase):
    def test_retain_option_cannot_be_sent_to_reschedule_operations(self):
        option = _retain_option()
        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "reschedule_operations",
                        "args": {
                            "option_id": option["option_id"],
                            "reason": "The existing allocation remains feasible.",
                        },
                        "id": "retain-write-attempt",
                        "type": "tool_call",
                    }],
                )
            ],
            "vessel_name": "MARINE PARADE",
            "imo_number": "9825063",
            "new_eta": REVISED_ETA,
            "ranked_result": {"options": [option]},
            "errors": [],
        }

        update = validate_tool_call_node(state)

        self.assertFalse(update["tool_call_valid"])
        self.assertIn("requires no database write", update["errors"][-1])
        self.assertIn("complete_no_action", update["errors"][-1])

    def test_reschedule_selection_resolves_option_from_ranked_state(self):
        option = {
            **_retain_option(),
            "option_id": "reallocate_one_vessel_1",
            "strategy": "reallocate_one_vessel",
        }
        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "reschedule_operations",
                        "args": {
                            "option_id": option["option_id"],
                            "reason": "Highest-ranked valid option.",
                        },
                        "id": "valid-selection",
                        "type": "tool_call",
                    }],
                )
            ],
            "vessel_name": "MARINE PARADE",
            "imo_number": "9825063",
            "new_eta": REVISED_ETA,
            "ranked_result": {"options": [option]},
            "errors": [],
        }

        update = validate_tool_call_node(state)

        self.assertTrue(update["tool_call_valid"])
        self.assertIs(update["selected_option"], option)
        self.assertEqual(update["selected_option_id"], option["option_id"])
        self.assertEqual(update["decision_reason"], "Highest-ranked valid option.")

    def test_unknown_reschedule_option_id_is_rejected(self):
        option = {
            **_retain_option(),
            "option_id": "shift_same_resources_1",
            "strategy": "shift_same_resources",
        }
        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{
                        "name": "reschedule_operations",
                        "args": {
                            "option_id": "invented_option",
                            "reason": "Try an option that was not ranked.",
                        },
                        "id": "invalid-selection",
                        "type": "tool_call",
                    }],
                )
            ],
            "vessel_name": "MARINE PARADE",
            "imo_number": "9825063",
            "new_eta": REVISED_ETA,
            "ranked_result": {"options": [option]},
            "errors": [],
        }

        update = validate_tool_call_node(state)

        self.assertFalse(update["tool_call_valid"])
        self.assertIn("option_id does not match", update["errors"][-1])

    def test_no_action_response_is_derived_from_state(self):
        state = {
            "messages": [
                AIMessage(
                    content=(
                        "The schedule was verified successfully and the allocation "
                        "was applied."
                    )
                )
            ],
            "vessel_name": "MARINE PARADE",
            "imo_number": "9825063",
            "new_eta": REVISED_ETA,
            "outcome": "no_action",
            "flagged_resources": [],
            "errors": [],
        }

        final_result = finalize_node(state)["final_result"]

        self.assertEqual(final_result["outcome"], "no_action")
        self.assertEqual(
            final_result["agent_response"],
            "MARINE PARADE: no action required. The existing berth, pilot, and "
            "tug allocations remain feasible for the revised ETA. No schedule "
            "changes were applied.",
        )
        self.assertNotIn("verified", final_result["agent_response"].lower())
        self.assertNotIn(
            "allocation was applied",
            final_result["agent_response"].lower(),
        )
