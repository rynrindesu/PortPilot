from PortPilot.agent.agent import (
    run_port_call_agent,
    agent_start_inspection,
    agent_complete_inspection,
    agent_advance_port_call,
)

from PortPilot.workflow.state import (
    PortCallState,
    PortCallStatus,
)


def determine_next_step(
    state: PortCallState,
    agent_result: dict,
):
    """
    Determine the next workflow step based on
    the structured result returned by the agent.

    This function does not override the deterministic
    compliance or workflow rules.
    """

    action = agent_result["agent_action"]

    if action == "REQUEST_CORRECTION":
        return "correction_required"

    if action == "REQUEST_INSPECTION":
        return "inspection_required"

    if action == "REQUEST_HUMAN_REVIEW":
        return "human_review"

    if action == "PROCEED":
        return "advance"

    return "stop"


def run_agent_graph(
    state: PortCallState,
):
    """
    Execute the PortPilot agent graph for the
    current port-call state.

    Flow:

        PortCallState
            ↓
        Agent check
            ↓
        Determine next action
            ↓
        correction / inspection /
        human review / advance
    """

    agent_result = run_port_call_agent(
        state
    )

    next_step = determine_next_step(
        state,
        agent_result,
    )

    # ---------------------------------------------
    # Correction required
    # ---------------------------------------------

    if next_step == "correction_required":

        return {
            "graph_status": "WAITING_FOR_CORRECTION",
            "next_step": next_step,
            "agent": agent_result,
            "state": state,
        }

    # ---------------------------------------------
    # Physical inspection required
    # ---------------------------------------------

    if next_step == "inspection_required":

        return {
            "graph_status": "WAITING_FOR_INSPECTION",
            "next_step": next_step,
            "agent": agent_result,
            "state": state,
        }

    # ---------------------------------------------
    # Human review required
    # ---------------------------------------------

    if next_step == "human_review":

        return {
            "graph_status": "WAITING_FOR_HUMAN_REVIEW",
            "next_step": next_step,
            "agent": agent_result,
            "state": state,
        }

    # ---------------------------------------------
    # Automatically attempt normal advancement
    # ---------------------------------------------

    if next_step == "advance":

        advance_result = agent_advance_port_call(
            state
        )

        return {
            "graph_status": (
                "ADVANCED"
                if advance_result["success"]
                else "ADVANCE_BLOCKED"
            ),
            "next_step": next_step,
            "advance": advance_result,
            "agent": agent_result,
            "state": state,
        }

    # ---------------------------------------------
    # Unknown / unsupported action
    # ---------------------------------------------

    return {
        "graph_status": "STOPPED",
        "next_step": next_step,
        "agent": agent_result,
        "state": state,
    }


def run_inspection_start(
    state: PortCallState,
):
    """
    Execute the inspection-start branch
    of the agent graph.

    The underlying inspection workflow remains
    responsible for enforcing whether inspection
    may actually start.
    """

    result = agent_start_inspection(
        state
    )

    return {
        "graph_status": (
            "INSPECTION_IN_PROGRESS"
            if result["success"]
            else "INSPECTION_START_BLOCKED"
        ),
        "inspection": result,
        "state": state,
    }


def run_inspection_completion(
    state: PortCallState,
    *,
    cleared: bool,
    findings: str | None = None,
):
    """
    Execute the human inspection completion branch.

    Human input is required for `cleared`.
    The AI agent does not decide whether the
    physical inspection passed.
    """

    result = agent_complete_inspection(
        state,
        cleared=cleared,
        findings=findings,
    )

    if not result["success"]:
        return {
            "graph_status": (
                "INSPECTION_COMPLETION_BLOCKED"
            ),
            "inspection": result,
            "state": state,
        }

    if (
        state.status
        == PortCallStatus.INSPECTION_CLEARED
    ):
        graph_status = "INSPECTION_CLEARED"

    elif (
        state.status
        == PortCallStatus.INSPECTION_REJECTED
    ):
        graph_status = "INSPECTION_REJECTED"

    else:
        graph_status = "INSPECTION_COMPLETED"

    return {
        "graph_status": graph_status,
        "inspection": result,
        "state": state,
    }