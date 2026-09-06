from PortPilot.models.documents import (
    ExtractedDocument,
    ExtractedField,
)

from PortPilot.workflow.state import (
    PortCallPhase,
    PortCallStatus,
    PortCallState,
)

from PortPilot.workflow.orchestrator import (
    process_port_call,
    advance_port_call,
)


def field(value):

    return ExtractedField(
        value=value,
        confidence=0.95,
        source_text=str(value),
    )


def create_compliant_arrival_documents():

    registry = ExtractedDocument(
        document_type="certificate_of_registry",
        vessel_name=field("EVER EXAMPLE"),
        imo_number=field("9876543"),
        call_sign=field("9V1234"),
        flag=field("Singapore"),
    )

    arrival = ExtractedDocument(
        document_type="arrival_general_declaration",
        vessel_name=field("EVER EXAMPLE"),
        imo_number=field("9876543"),
        call_sign=field("9V1234"),
        gross_tonnage=field(50000),
        flag=field("Singapore"),
        vessel_type=field("container"),
        port_of_registry=field("Singapore"),
        official_number=field("123456"),
        purpose_of_call=field("cargo"),
        arrival_date_time=field(
            "2026-09-04T10:00"
        ),
        last_port=field("Shanghai"),
        master=field("John Smith"),
        crew=field(20),
        passengers=field(0),
        total_cargo=field("8000 kg"),
    )

    return [registry, arrival]


def test_create_port_call_state():

    state = PortCallState(
        port_call_id="PC-0001",
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,
        first_singapore_call=False,
        purpose_of_call="cargo",
    )

    assert state.port_call_id == "PC-0001"
    assert state.vessel_name == "EVER EXAMPLE"
    assert state.imo_number == "9876543"

    assert state.phase == PortCallPhase.ARRIVAL

    assert state.status == (
        PortCallStatus.ARRIVAL_PENDING
    )

    assert state.documents == []


def test_process_compliant_arrival():

    state = PortCallState(
        port_call_id="PC-0001",
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,
        purpose_of_call="cargo",
    )

    documents = (
        create_compliant_arrival_documents()
    )

    result = process_port_call(
        state,
        documents,
    )

    assert (
        result["compliance"].status
        == "PASS"
    )

    assert (
        result["escalation"]["action"]
        == "NO_ESCALATION"
    )

    assert (
        state.status
        == PortCallStatus.ARRIVAL_CLEARED
    )


def test_process_arrival_with_inspection():

    state = PortCallState(
        port_call_id="PC-0002",
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,
        purpose_of_call="cargo",
    )

    documents = (
        create_compliant_arrival_documents()
    )

    result = process_port_call(
        state,
        documents,
        physical_inspection_required=True,
    )

    assert (
        result["compliance"].status
        == "PASS"
    )

    assert (
        result["escalation"]["action"]
        == "INSPECTION_REQUIRED"
    )

    assert (
        state.status
        == PortCallStatus.INSPECTION_REQUIRED
    )


def test_process_arrival_with_missing_documents():

    state = PortCallState(
        port_call_id="PC-0003",
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,
        first_singapore_call=True,
    )

    arrival = ExtractedDocument(
        document_type="arrival_general_declaration",
        vessel_name=field("EVER EXAMPLE"),
        imo_number=field("9876543"),
    )

    result = process_port_call(
        state,
        [arrival],
    )

    assert (
        result["compliance"].status
        == "CORRECTION_REQUIRED"
    )

    assert (
        result["escalation"]["action"]
        == "CORRECTION_REQUIRED"
    )

    assert (
        state.status
        == PortCallStatus.CORRECTION_REQUIRED
    )
    
def test_advance_arrival_to_operations():

    state = PortCallState(
        port_call_id="PC-0004",
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_CLEARED,
    )

    result = advance_port_call(state)

    assert result["success"] is True

    assert state.phase == PortCallPhase.OPERATIONS

    assert state.status == PortCallStatus.OPERATIONS
    
def test_advance_operations_to_departure():

    state = PortCallState(
        port_call_id="PC-0005",
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase=PortCallPhase.OPERATIONS,
        status=PortCallStatus.OPERATIONS,
    )

    result = advance_port_call(state)

    assert result["success"] is True

    assert state.phase == PortCallPhase.DEPARTURE

    assert state.status == PortCallStatus.DEPARTURE_PENDING
    
def test_advance_departure_to_completed():

    state = PortCallState(
        port_call_id="PC-0006",
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase=PortCallPhase.DEPARTURE,
        status=PortCallStatus.DEPARTURE_CLEARED,
    )

    result = advance_port_call(state)

    assert result["success"] is True

    assert state.status == PortCallStatus.COMPLETED
    
def test_cannot_advance_uncleared_arrival():

    state = PortCallState(
        port_call_id="PC-0007",
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.CORRECTION_REQUIRED,
    )

    result = advance_port_call(state)

    assert result["success"] is False

    assert state.phase == PortCallPhase.ARRIVAL

    assert (
        state.status
        == PortCallStatus.CORRECTION_REQUIRED
    )

def test_inspection_cleared_advances_to_operations():

    state = PortCallState(
        port_call_id="PC-0003",
        vessel_name="EVER INSPECTED",
        imo_number="9876545",
        call_sign="9V9999",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.INSPECTION_CLEARED,
        purpose_of_call="cargo",
    )

    result = advance_port_call(state)

    assert result["success"] is True

    assert (
        state.phase
        == PortCallPhase.OPERATIONS
    )

    assert (
        state.status
        == PortCallStatus.OPERATIONS
    )
    
def test_inspection_rejected_cannot_advance():

    state = PortCallState(
        port_call_id="PC-0004",
        vessel_name="EVER REJECTED",
        imo_number="9876546",
        call_sign="9V1111",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.INSPECTION_REJECTED,
        purpose_of_call="cargo",
    )

    result = advance_port_call(state)

    assert result["success"] is False

    assert (
        state.phase
        == PortCallPhase.ARRIVAL
    )

    assert (
        state.status
        == PortCallStatus.INSPECTION_REJECTED
    )
    
