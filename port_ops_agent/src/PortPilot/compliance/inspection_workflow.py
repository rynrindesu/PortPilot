from PortPilot.workflow.state import (
    PortCallState,
    PortCallStatus,
    add_event,
)


def start_inspection(
    state: PortCallState,
):
    if state.status != PortCallStatus.INSPECTION_REQUIRED:
        return {
            "success": False,
            "message": (
                "Inspection cannot be started because "
                "the port call does not require inspection."
            ),
        }

    state.status = PortCallStatus.INSPECTION_IN_PROGRESS

    add_event(
        state,
        event="INSPECTION_STARTED",
        description="Physical inspection started.",
        source="human_workflow",
    )

    return {
        "success": True,
        "message": "Physical inspection started.",
        "status": state.status.value,
    }


def complete_inspection(
    state: PortCallState,
    *,
    cleared: bool,
    findings: str | None = None,
):
    if state.status != PortCallStatus.INSPECTION_IN_PROGRESS:
        return {
            "success": False,
            "message": (
                "Inspection cannot be completed because "
                "an inspection is not currently in progress."
            ),
        }

    if cleared:
        state.status = PortCallStatus.INSPECTION_CLEARED

        add_event(
            state,
            event="INSPECTION_CLEARED",
            description="Physical inspection cleared.",
            source="human_inspector",
        )

        return {
            "success": True,
            "message": "Physical inspection cleared.",
            "status": state.status.value,
            "findings": findings,
        }

    state.status = PortCallStatus.INSPECTION_REJECTED

    add_event(
        state,
        event="INSPECTION_REJECTED",
        description=(
            "Physical inspection identified an issue."
        ),
        source="human_inspector",
    )

    return {
        "success": True,
        "message": (
            "Physical inspection identified an issue."
        ),
        "status": state.status.value,
        "findings": findings,
    }