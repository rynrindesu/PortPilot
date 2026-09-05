from PortPilot.compliance.engine import (
    run_compliance_check,
)

from PortPilot.compliance.escalation import (
    determine_escalation,
)

from PortPilot.compliance.port_call import (
    PortCall,
)

from PortPilot.workflow.state import (
    PortCallPhase,
    PortCallState,
    PortCallStatus,
    add_event,
)

from PortPilot.compliance.risk import (
    calculate_risk_score,
)

from PortPilot.compliance.inspection import (
    determine_inspection_decision,
)

def process_port_call(
    state: PortCallState,
    documents: list,
    physical_inspection_required: bool = False,
):
    """
    Process the current stage of a port call.

    The orchestrator:
        1. Runs compliance checks.
        2. Calculates risk.
        3. Determines inspection requirements.
        4. Determines escalation.
        5. Updates the port-call status.
    """

    port_call = PortCall(
        vessel_name=state.vessel_name,
        imo_number=state.imo_number,
        call_sign=state.call_sign,
        phase=state.phase.value,
        first_singapore_call=(
            state.first_singapore_call
        ),
        purpose_of_call=state.purpose_of_call,
        carrying_dangerous_goods=(
            state.carrying_dangerous_goods
        ),
        radioactive_material=(
            state.radioactive_material
        ),
    )

    # --------------------------------------------------
    # 1. Compliance
    # --------------------------------------------------

    compliance_result = run_compliance_check(
        port_call,
        documents,
    )

    # --------------------------------------------------
    # 2. Check document inconsistency
    # --------------------------------------------------

    document_inconsistency = any(
        issue.code == "FIELD_MISMATCH"
        for issue in compliance_result.issues
    )

    # --------------------------------------------------
    # 3. Risk assessment
    # --------------------------------------------------

    risk_result = calculate_risk_score(
        port_call,
        compliance_status=(
            compliance_result.status
        ),
        document_inconsistency=(
            document_inconsistency
        ),
    )

    # --------------------------------------------------
    # 4. Inspection decision
    # --------------------------------------------------

    inspection_decision = (
        determine_inspection_decision(
            port_call,
            risk_level=risk_result["risk_level"],
            compliance_status=(
                compliance_result.status
            ),
        )
    )

    # --------------------------------------------------
    # 5. Escalation
    # --------------------------------------------------

    escalation = determine_escalation(
        compliance_status=(
            compliance_result.status
        ),
        physical_inspection_required=(
            physical_inspection_required
            or inspection_decision["decision"]
            == "inspection_required"
        ),
    )

    # --------------------------------------------------
    # 6. Update state
    # --------------------------------------------------

    if escalation["action"] == "INSPECTION_REQUIRED":

        state.status = (
            PortCallStatus.INSPECTION_REQUIRED
        )

    elif escalation["action"] == "CORRECTION_REQUIRED":

        state.status = (
            PortCallStatus.CORRECTION_REQUIRED
        )

    elif escalation["action"] == "HUMAN_REVIEW":

        state.status = (
            PortCallStatus.HUMAN_REVIEW
        )

    else:

        if state.phase.value == "arrival":

            state.status = (
                PortCallStatus.ARRIVAL_CLEARED
            )

        elif state.phase.value == "operations":

            state.status = (
                PortCallStatus.OPERATIONS
            )

        elif state.phase.value == "departure":

            state.status = (
                PortCallStatus.DEPARTURE_CLEARED
            )

    state.documents = documents

    return {
        "port_call": state,
        "compliance": compliance_result,
        "risk": risk_result,
        "inspection": inspection_decision,
        "escalation": escalation,
    }

def advance_port_call(
    state: PortCallState,
):
    """
    Advance a port call to the next workflow phase.

    A port call can only advance when its current
    phase has been successfully cleared.
    """

    if (
        state.phase.value == "arrival"
        and state.status in (
            PortCallStatus.ARRIVAL_CLEARED,
            PortCallStatus.INSPECTION_CLEARED,
        )
    ):
        state.phase = PortCallPhase.OPERATIONS
        state.status = PortCallStatus.OPERATIONS

        add_event(
            state,
            event="PORT_CALL_ADVANCED",
            description=(
                "Arrival cleared. "
                "Port call advanced to operations."
            ),
            source="workflow",
        )

        return {
            "success": True,
            "message": (
                "Arrival cleared. "
                "Port call advanced to operations."
            ),
        }

    if (
        state.phase.value == "operations"
        and state.status
        == PortCallStatus.OPERATIONS
    ):
        state.phase = PortCallPhase.DEPARTURE
        state.status = PortCallStatus.DEPARTURE_PENDING

        add_event(
            state,
            event="PORT_CALL_ADVANCED",
            description=(
                "Operations completed. "
                "Port call advanced to departure."
            ),
            source="workflow",
        )

        return {
            "success": True,
            "message": (
                "Operations completed. "
                "Port call advanced to departure."
            ),
        }

    if (
        state.phase.value == "departure"
        and state.status
        == PortCallStatus.DEPARTURE_CLEARED
    ):
        state.status = PortCallStatus.COMPLETED

        add_event(
            state,
            event="PORT_CALL_COMPLETED",
            description=(
                "Departure cleared. "
                "Port call completed."
            ),
            source="workflow",
        )

        return {
            "success": True,
            "message": (
                "Departure cleared. "
                "Port call completed."
            ),
        }

    return {
        "success": False,
        "message": (
            f"Port call cannot advance from "
            f"phase '{state.phase.value}' "
            f"with status '{state.status.value}'."
        ),
    }