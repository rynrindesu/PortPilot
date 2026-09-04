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
)

def process_port_call(
    state: PortCallState,
    documents: list,
    physical_inspection_required: bool = False,
):
    """
    Process the current stage of a port call.

    The orchestrator:
        1. Runs the compliance engine.
        2. Determines escalation.
        3. Updates the port-call status.
        4. Returns the results.
    """

    # --------------------------------
    # 1. Build compliance PortCall
    # --------------------------------

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

    # --------------------------------
    # 2. Run compliance
    # --------------------------------

    compliance_result = run_compliance_check(
        port_call,
        documents,
    )

    # --------------------------------
    # 3. Determine escalation
    # --------------------------------

    escalation = determine_escalation(
        compliance_status=(
            compliance_result.status
        ),
        physical_inspection_required=(
            physical_inspection_required
        ),
    )

    # --------------------------------
    # 4. Update workflow status
    # --------------------------------

    if escalation["action"] == "CORRECTION_REQUIRED":

        state.status = (
            PortCallStatus.CORRECTION_REQUIRED
        )

    elif escalation["action"] == "HUMAN_REVIEW":

        state.status = (
            PortCallStatus.HUMAN_REVIEW
        )

    elif escalation["action"] == "INSPECTION_REQUIRED":

        state.status = (
            PortCallStatus.INSPECTION_REQUIRED
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

    # --------------------------------
    # 5. Store documents in state
    # --------------------------------

    state.documents = documents

    # --------------------------------
    # 6. Return workflow result
    # --------------------------------

    return {
        "port_call": state,
        "compliance": compliance_result,
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

    # --------------------------------
    # ARRIVAL → OPERATIONS
    # --------------------------------

    if (
        state.phase.value == "arrival"
        and state.status
        == PortCallStatus.ARRIVAL_CLEARED
    ):

        state.phase = PortCallPhase.OPERATIONS
        state.status = PortCallStatus.OPERATIONS

        return {
            "success": True,
            "message": (
                "Arrival cleared. "
                "Port call advanced to operations."
            ),
        }

    # --------------------------------
    # OPERATIONS → DEPARTURE
    # --------------------------------

    if (
        state.phase.value == "operations"
        and state.status
        == PortCallStatus.OPERATIONS
    ):

        state.phase = PortCallPhase.DEPARTURE
        state.status = PortCallStatus.DEPARTURE_PENDING

        return {
            "success": True,
            "message": (
                "Operations completed. "
                "Port call advanced to departure."
            ),
        }

    # --------------------------------
    # DEPARTURE → COMPLETED
    # --------------------------------

    if (
        state.phase.value == "departure"
        and state.status
        == PortCallStatus.DEPARTURE_CLEARED
    ):

        state.status = PortCallStatus.COMPLETED

        return {
            "success": True,
            "message": (
                "Departure cleared. "
                "Port call completed."
            ),
        }

    # --------------------------------
    # Cannot advance
    # --------------------------------

    return {
        "success": False,
        "message": (
            f"Port call cannot advance from "
            f"phase '{state.phase.value}' "
            f"with status '{state.status.value}'."
        ),
    }