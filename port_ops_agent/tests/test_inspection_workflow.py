from PortPilot.workflow.state import (
    PortCallPhase,
    PortCallState,
    PortCallStatus,
)

from PortPilot.compliance.inspection_workflow import (
    start_inspection,
    complete_inspection,
)


def create_inspection_state():
    return PortCallState(
        port_call_id="PC-INSPECT-001",
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.INSPECTION_REQUIRED,
    )


def test_start_inspection():

    state = create_inspection_state()

    result = start_inspection(state)

    assert result["success"] is True
    assert state.status == (
        PortCallStatus.INSPECTION_IN_PROGRESS
    )


def test_cannot_start_unrequired_inspection():

    state = create_inspection_state()

    state.status = PortCallStatus.ARRIVAL_CLEARED

    result = start_inspection(state)

    assert result["success"] is False
    assert state.status == (
        PortCallStatus.ARRIVAL_CLEARED
    )


def test_complete_inspection_cleared():

    state = create_inspection_state()

    start_inspection(state)

    result = complete_inspection(
        state,
        cleared=True,
        findings="Cargo verified against declaration.",
    )

    assert result["success"] is True
    assert state.status == (
        PortCallStatus.INSPECTION_CLEARED
    )


def test_complete_inspection_rejected():

    state = create_inspection_state()

    start_inspection(state)

    result = complete_inspection(
        state,
        cleared=False,
        findings="Cargo discrepancy identified.",
    )

    assert result["success"] is True
    assert state.status == (
        PortCallStatus.INSPECTION_REJECTED
    )


def test_cannot_complete_inspection_before_start():

    state = create_inspection_state()

    result = complete_inspection(
        state,
        cleared=True,
    )

    assert result["success"] is False
    assert state.status == (
        PortCallStatus.INSPECTION_REQUIRED
    )