from PortPilot.workflow.orchestrator import (
    process_port_call,
    advance_port_call,
)

from PortPilot.compliance.inspection_workflow import (
    start_inspection,
    complete_inspection,
)


def check_port_call_tool(
    state,
):
    """
    Run the existing deterministic compliance,
    risk, inspection, and escalation pipeline.
    """

    return process_port_call(
        state,
        state.documents,
    )


def start_inspection_tool(
    state,
):
    """
    Start a human physical inspection.
    """

    return start_inspection(state)


def complete_inspection_tool(
    state,
    *,
    cleared: bool,
    findings: str | None = None,
):
    """
    Record the result of a human inspection.
    """

    return complete_inspection(
        state,
        cleared=cleared,
        findings=findings,
    )


def advance_port_call_tool(
    state,
):
    """
    Advance the port call if the current
    workflow state allows it.
    """

    return advance_port_call(state)