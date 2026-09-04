"""Simulate PortPilot agent decisions and exercise every graph outcome.

This suite does not call a live language model. Instead, each test constructs
the same ``AIMessage`` (including structured tool calls) that a tool-enabled
chat model would return. Tool results are represented by real ``ToolMessage``
objects and then passed through PortPilot's actual validation, routing,
result-processing, verification, and finalization functions.

Database-changing tools are never invoked. Their expected result messages are
simulated, and post-write database reads are mocked. The read-free
``complete_no_action`` tool is invoked directly so its real output contract is
covered. This makes the tests deterministic and safe while accurately testing
the protocol between the future model, LangGraph, and PortPilot's tools.

Run from the repository root:

    PYTHONPATH=backend/src .venv/bin/python \
        backend/tests/graph_with_ai_simulation/graph_tools_tests.py

The run writes a human-readable report to ``graph_tools_output.txt`` in this
directory.
"""

from __future__ import annotations

import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from langchain_core.messages import AIMessage, ToolMessage

from PortPilot.agent.graph import (
    MAX_AGENT_ITERATIONS,
    finalize_node,
    initial_state,
    process_tool_result_node,
    route_after_chatbot,
    route_after_tool_result,
    route_after_tool_validation,
    validate_tool_call_node,
    verify_node,
)
from PortPilot.agent.tools import complete_no_action


OUTPUT_PATH = Path(__file__).with_name("graph_tools_output.txt")
SAMPLE_OUTCOMES: dict[str, dict] = {}

VESSEL_NAME = "AI SIMULATION VESSEL"
IMO_NUMBER = "9000001"
PREVIOUS_ETA = "2026-09-04T09:00:00+00:00"
NEW_ETA = "2026-09-04T12:00:00+00:00"


def _allocation(resource_id: str, start: str, end: str) -> dict:
    return {
        "resource_id": resource_id,
        "start_time": start,
        "end_time": end,
        "buffer_minutes": 15,
    }


EXPECTED_ALLOCATIONS = {
    "berth": _allocation(
        "B01", "2026-09-04T12:00:00+00:00", "2026-09-04T20:00:00+00:00"
    ),
    "pilot": _allocation(
        "P01", "2026-09-04T11:00:00+00:00", "2026-09-04T12:00:00+00:00"
    ),
    "tug": _allocation(
        "T01", "2026-09-04T12:00:00+00:00", "2026-09-04T13:00:00+00:00"
    ),
}


def _option(option_id: str, strategy: str) -> dict:
    """Return a complete option shaped like get_ranked_options output."""

    return {
        "option_id": option_id,
        "strategy": strategy,
        "target_eta": NEW_ETA,
        "affected_vessels": [
            {"vessel_name": VESSEL_NAME, "imo_number": IMO_NUMBER}
        ],
        "changes": [
            {
                "vessel_name": VESSEL_NAME,
                "imo_number": IMO_NUMBER,
                "allocations": copy.deepcopy(EXPECTED_ALLOCATIONS),
            }
        ],
        "resource_conflicts": [],
        "rank": 1,
        "scores": {
            "affected_vessel_count": 1,
            "total_schedule_shift": 180.0,
            "repeat_changes": 1,
            "resource_utilisation": 60.0,
        },
    }


def _schedule_result(allocations: dict | None = None) -> dict:
    """Return the JSON object produced by get_vessel_schedule."""

    actual_allocations = copy.deepcopy(allocations or EXPECTED_ALLOCATIONS)
    for allocation in actual_allocations.values():
        allocation.setdefault("status", "confirmed")

    return {
        "found": True,
        "valid": True,
        "vessel": {
            "vessel_name": VESSEL_NAME,
            "imo_number": IMO_NUMBER,
            "previous_eta": PREVIOUS_ETA,
            "current_eta": NEW_ETA,
        },
        "allocations": actual_allocations,
    }


class GraphToolsAISimulationTests(unittest.TestCase):
    """Exercise all AgentOutcome values using scripted model decisions."""

    def _new_state(self) -> dict:
        # Step 1: monitoring would emit this event after observing an ETA change.
        return initial_state({
            "event": "ETA_CHANGED",
            "vessel_name": VESSEL_NAME,
            "imo_number": IMO_NUMBER,
            "previous_eta": PREVIOUS_ETA,
            "new_eta": NEW_ETA,
        })

    def _simulate_ai_tool_turn(
        self,
        state: dict,
        tool_name: str,
        arguments: dict,
        tool_result: dict | str,
    ) -> str:
        """Simulate one model decision followed by one ToolNode result."""

        # Step A: simulate chatbot_node returning a structured tool request.
        state["iteration_count"] = state.get("iteration_count", 0) + 1
        tool_call_id = f"simulated-{tool_name}-{state['iteration_count']}"
        state["messages"].append(AIMessage(
            content=f"I will call {tool_name} and evaluate its result.",
            tool_calls=[{
                "name": tool_name,
                "args": copy.deepcopy(arguments),
                "id": tool_call_id,
                "type": "tool_call",
            }],
        ))

        # Step B: exercise the actual chatbot conditional-edge decision.
        self.assertEqual(route_after_chatbot(state), "validate_tools")

        # Step C: exercise the actual graph authorization boundary.
        validation_update = validate_tool_call_node(state)
        self.assertTrue(
            validation_update.get("tool_call_valid"),
            validation_update.get("errors"),
        )
        state.update(validation_update)
        self.assertEqual(route_after_tool_validation(state), "tools")

        # Step D: simulate the ToolMessage that ToolNode would append. Write
        # tools are not invoked, keeping the suite isolated from the database.
        content = tool_result if isinstance(tool_result, str) else json.dumps(tool_result)
        state["messages"].append(ToolMessage(
            content=content,
            name=tool_name,
            tool_call_id=tool_call_id,
        ))

        # Step E: exercise actual result parsing and post-tool routing.
        state.update(process_tool_result_node(state))
        return route_after_tool_result(state)

    def _simulate_final_ai_response(self, state: dict, response: str) -> dict:
        """Simulate the model evaluating observations and ending the run."""

        # Step 1: the model produces an ordinary response with no tool call.
        state["iteration_count"] = state.get("iteration_count", 0) + 1
        state["messages"].append(AIMessage(content=response))

        # Step 2: the chatbot router recognizes that the agent is finished.
        self.assertEqual(route_after_chatbot(state), "finalize")

        # Step 3: the real finalizer derives a stable external result.
        update = finalize_node(state)
        state.update(update)
        return update["final_result"]

    def _simulate_schedule_and_ranking(
        self,
        state: dict,
        ranked_result: dict,
    ) -> None:
        """Simulate the normal inspect-then-rank beginning of a graph run."""

        route = self._simulate_ai_tool_turn(
            state,
            "get_vessel_schedule",
            {"vessel_name": VESSEL_NAME, "imo_number": IMO_NUMBER},
            _schedule_result(),
        )
        self.assertEqual(route, "chatbot")

        route = self._simulate_ai_tool_turn(
            state,
            "get_ranked_options",
            {
                "vessel_name": VESSEL_NAME,
                "imo_number": IMO_NUMBER,
                "new_eta": NEW_ETA,
            },
            ranked_result,
        )
        self.assertEqual(route, "chatbot")

    def _record(self, name: str, result: dict) -> None:
        SAMPLE_OUTCOMES[name] = copy.deepcopy(result)

    def test_01_rescheduled(self) -> None:
        """A valid selected option is applied, read back, and verified."""

        state = self._new_state()
        selected_option = _option("shift_same_resources", "shift_same_resources")

        # Step 1: simulated AI inspects the schedule and requests ranked plans.
        self._simulate_schedule_and_ranking(state, {
            "found": True,
            "valid": True,
            "generated_option_count": 4,
            "valid_option_count": 2,
            "invalid_option_count": 2,
            "invalid_reasons": [],
            "options": [selected_option],
        })

        # Step 2: simulated AI selects the exact ranked option. The write
        # result is simulated so this test never changes a real allocation.
        route = self._simulate_ai_tool_turn(
            state,
            "reschedule_operations",
            {
                "option": selected_option,
                "reason": "Rank 1 minimizes affected vessels and schedule movement.",
            },
            {
                "success": True,
                "option_id": "shift_same_resources",
                "changes_applied": [
                    {"vessel_name": VESSEL_NAME, "resource_type": kind}
                    for kind in ("berth", "pilot", "tug")
                ],
            },
        )
        self.assertEqual(route, "verify")

        # Step 3: verification performs a fresh read. Mocked data exactly
        # matches the option and all allocations are confirmed.
        fake_schedule_tool = Mock()
        fake_schedule_tool.invoke.return_value = json.dumps(_schedule_result())
        with patch(
            "PortPilot.agent.graph.get_vessel_schedule_tool",
            fake_schedule_tool,
        ):
            state.update(verify_node(state))

        self.assertTrue(state["verification_result"]["verified"])

        # Step 4: simulated AI evaluates verification and reports success.
        result = self._simulate_final_ai_response(
            state,
            "The ranked schedule was applied and independently verified.",
        )
        self.assertEqual(result["outcome"], "rescheduled")
        self._record("rescheduled", result)

    def test_02_no_action(self) -> None:
        """A valid retain option ends intentionally without database writes."""

        state = self._new_state()
        retain_option = _option(
            "retain_current_allocation",
            "retain_current_allocation",
        )

        # Step 1: simulated AI discovers that retaining the current schedule
        # is a valid ranked option.
        self._simulate_schedule_and_ranking(state, {
            "found": True,
            "valid": True,
            "generated_option_count": 3,
            "valid_option_count": 1,
            "invalid_option_count": 2,
            "invalid_reasons": [],
            "options": [retain_option],
        })

        # Step 2: call the real read-free completion tool. Graph validation
        # proves this option ID belongs to a valid retain option.
        reason = "The existing confirmed allocations remain feasible for the revised ETA."
        real_tool_result = complete_no_action.invoke({
            "option_id": "retain_current_allocation",
            "reason": reason,
        })
        route = self._simulate_ai_tool_turn(
            state,
            "complete_no_action",
            {
                "option_id": "retain_current_allocation",
                "reason": reason,
            },
            real_tool_result,
        )
        self.assertEqual(route, "chatbot")
        self.assertFalse(state["write_attempted"])

        # Step 3: simulated AI explains why no operational write was needed.
        result = self._simulate_final_ai_response(
            state,
            "The current allocations remain valid, so no schedule change was required.",
        )
        self.assertEqual(result["outcome"], "no_action")
        self._record("no_action", result)

    def test_03_pending_review(self) -> None:
        """No valid plan exists, so the AI escalates the affected resource."""

        state = self._new_state()

        # Step 1: ranking reports that every automatic option is invalid.
        self._simulate_schedule_and_ranking(state, {
            "found": True,
            "valid": True,
            "generated_option_count": 3,
            "valid_option_count": 0,
            "invalid_option_count": 3,
            "invalid_reasons": [
                "The berth booking starts within the two-hour freeze window."
            ],
            "options": [],
        })

        # Step 2: simulated AI calls the review tool using the concrete
        # rejection reason. The result is simulated to avoid a database write.
        route = self._simulate_ai_tool_turn(
            state,
            "flag_for_review",
            {
                "resource_type": "berth",
                "vessel_name": VESSEL_NAME,
                "imo_number": IMO_NUMBER,
                "reason": "The berth booking starts within the two-hour freeze window.",
            },
            {
                "success": True,
                "outcome": "human_review",
                "vessel_name": VESSEL_NAME,
                "imo_number": IMO_NUMBER,
                "resource_type": "berth",
                "resource_id": "B01",
                "reason": "The berth booking starts within the two-hour freeze window.",
            },
        )
        self.assertEqual(route, "chatbot")
        self.assertEqual(state["flagged_resources"], ["berth"])

        # Step 3: simulated AI reports the successful escalation.
        result = self._simulate_final_ai_response(
            state,
            "No valid automatic plan exists; the berth was flagged for human review.",
        )
        self.assertEqual(result["outcome"], "pending_review")
        self._record("pending_review", result)

    def test_04_unable_to_resolve(self) -> None:
        """The agent reaches its safety limit without an action or escalation."""

        state = self._new_state()

        # Step 1: the AI successfully reads the schedule but never reaches a
        # valid operational decision.
        route = self._simulate_ai_tool_turn(
            state,
            "get_vessel_schedule",
            {"vessel_name": VESSEL_NAME, "imo_number": IMO_NUMBER},
            _schedule_result(),
        )
        self.assertEqual(route, "chatbot")

        # Step 2: simulate the iteration safety limit being reached. The model
        # responds without claiming that an action succeeded.
        state["iteration_count"] = MAX_AGENT_ITERATIONS - 1
        result = self._simulate_final_ai_response(
            state,
            "I could not determine a safe action within the allowed iterations.",
        )

        # Step 3: the finalizer distinguishes this from an intentional no-op.
        self.assertEqual(result["outcome"], "unable_to_resolve")
        self._record("unable_to_resolve", result)

    def test_05_failed(self) -> None:
        """A reported write whose database state does not match is failed."""

        state = self._new_state()
        selected_option = _option("alternative_resources_1", "alternative_resources")

        # Step 1: the AI inspects, ranks, and selects an exact valid option.
        self._simulate_schedule_and_ranking(state, {
            "found": True,
            "valid": True,
            "generated_option_count": 5,
            "valid_option_count": 1,
            "invalid_option_count": 4,
            "invalid_reasons": [],
            "options": [selected_option],
        })
        route = self._simulate_ai_tool_turn(
            state,
            "reschedule_operations",
            {
                "option": selected_option,
                "reason": "This is the only valid resource combination.",
            },
            {
                "success": True,
                "option_id": "alternative_resources_1",
                "changes_applied": [],
            },
        )
        self.assertEqual(route, "verify")

        # Step 2: the independent read finds an allocation still marked for
        # review. Resource IDs and times match, but status validity does not.
        unconfirmed = copy.deepcopy(EXPECTED_ALLOCATIONS)
        for allocation in unconfirmed.values():
            allocation["status"] = "confirmed"
        unconfirmed["berth"]["status"] = "pending_review"

        fake_schedule_tool = Mock()
        fake_schedule_tool.invoke.return_value = json.dumps(
            _schedule_result(unconfirmed)
        )
        with patch(
            "PortPilot.agent.graph.get_vessel_schedule_tool",
            fake_schedule_tool,
        ):
            state.update(verify_node(state))

        self.assertFalse(state["verification_result"]["verified"])
        self.assertTrue(any(
            "status does not match" in mismatch
            for mismatch in state["verification_result"]["mismatches"]
        ))

        # Step 3: the AI accurately reports that the write could not be
        # verified; finalization classifies the run as failed.
        result = self._simulate_final_ai_response(
            state,
            "The write was reported as successful, but verification failed.",
        )
        self.assertEqual(result["outcome"], "failed")
        self._record("failed", result)


def _write_output(test_output: str, successful: bool) -> None:
    """Write the test transcript and real final-result samples."""

    accuracy_notes = """AI SIMULATION METHOD
--------------------
The AI is simulated by deterministic AIMessage objects containing the exact
structured tool calls a bound chat model would emit. Real graph validation,
routing, result processing, verification, and finalization code is executed.
ToolMessage objects reproduce the interface through which ToolNode returns
observations to the model.

RATIONALE
---------
Scripted decisions isolate the graph contract from model randomness, API
availability, cost, and prompt variation. Database writes are represented by
controlled results, so outcome logic can be tested without altering operational
data. The complete_no_action tool is safe and is executed for real.

EVALUATION OF ACCURACY
----------------------
High fidelity: message shapes, tool arguments, tool-call validation, state
updates, conditional routes, option provenance, post-write comparison, and
final outcome classification.

Not covered: whether a real model chooses the correct tool or rationale, model
provider formatting differences, live ToolNode execution inside a compiled
StateGraph, database transaction behavior, concurrency, or network failures.
Those require later compiled-graph integration tests and a small set of live
model evaluations.
"""

    report = [
        "PORTPILOT GRAPH TOOL / AI SIMULATION RESULTS",
        "============================================",
        "",
        test_output.rstrip(),
        "",
        f"OVERALL RESULT: {'PASS' if successful else 'FAIL'}",
        "",
        accuracy_notes.rstrip(),
        "",
        "SAMPLE FINAL OUTCOMES",
        "---------------------",
        json.dumps(SAMPLE_OUTCOMES, indent=2, sort_keys=True),
        "",
    ]
    OUTPUT_PATH.write_text("\n".join(report), encoding="utf-8")


if __name__ == "__main__":
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        GraphToolsAISimulationTests
    )
    test_result = unittest.TextTestRunner(
        stream=stream,
        verbosity=2,
    ).run(suite)

    rendered_test_output = stream.getvalue()
    _write_output(rendered_test_output, test_result.wasSuccessful())
    print(OUTPUT_PATH.read_text(encoding="utf-8"))

    raise SystemExit(0 if test_result.wasSuccessful() else 1)
