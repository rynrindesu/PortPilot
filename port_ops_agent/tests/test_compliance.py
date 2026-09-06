from PortPilot.models.documents import (
    ExtractedDocument,
    ExtractedField,
)

from PortPilot.compliance.consistency import (
    check_document_consistency,
)

from PortPilot.compliance.port_call import (
    PortCall,
)

from PortPilot.compliance.engine import (
    run_compliance_check,
)

from PortPilot.compliance.escalation import (
    determine_escalation,
)
    
def field(value):

    return ExtractedField(
        value=value,
        confidence=0.95,
        source_text=str(value),
    )


def test_matching_documents():

    registry = ExtractedDocument(
        document_type="certificate_of_registry",
        vessel_name=field("EVER EXAMPLE"),
        imo_number=field("9876543"),
        call_sign=field("9V1234"),
        flag=field("Singapore"),
    )

    declaration = ExtractedDocument(
        document_type="arrival_general_declaration",
        vessel_name=field("EVER EXAMPLE"),
        imo_number=field("9876543"),
        call_sign=field("9V1234"),
        flag=field("Singapore"),
    )

    result = check_document_consistency(
        [registry, declaration]
    )

    assert result.status == "PASS"
    assert result.issues == []


def test_call_sign_mismatch():

    registry = ExtractedDocument(
        document_type="certificate_of_registry",
        vessel_name=field("EVER EXAMPLE"),
        imo_number=field("9876543"),
        call_sign=field("9V1234"),
    )

    declaration = ExtractedDocument(
        document_type="arrival_general_declaration",
        vessel_name=field("EVER EXAMPLE"),
        imo_number=field("9876543"),
        call_sign=field("9V5678"),
    )

    result = check_document_consistency(
        [registry, declaration]
    )

    assert result.status == "CORRECTION_REQUIRED"

    assert any(
        issue.field == "call_sign"
        for issue in result.issues
    )
    
def test_compliant_arrival():

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
        arrival_date_time=field("2026-09-04T10:00"),
        last_port=field("Shanghai"),
        master=field("John Smith"),
        crew=field(20),
        passengers=field(0),
        total_cargo=field("8000 kg"),
    )

    port_call = PortCall(
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase="arrival",
        first_singapore_call=False,
        purpose_of_call="cargo",
    )

    result = run_compliance_check(
        port_call,
        [registry, arrival],
    )

    assert result.status == "PASS"
    
def test_missing_required_document():

    arrival = ExtractedDocument(
        document_type="arrival_general_declaration",
        vessel_name=field("EVER EXAMPLE"),
        imo_number=field("9876543"),
    )

    port_call = PortCall(
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        phase="arrival",
        first_singapore_call=True,
    )

    result = run_compliance_check(
        port_call,
        [arrival],
    )

    assert result.status == "CORRECTION_REQUIRED"

    assert any(
        issue.code == "MISSING_REQUIRED_DOCUMENT"
        for issue in result.issues
    )
    
def test_inconsistent_imo():

    registry = ExtractedDocument(
        document_type="certificate_of_registry",
        vessel_name=field("EVER EXAMPLE"),
        imo_number=field("9876543"),
        call_sign=field("9V1234"),
    )

    arrival = ExtractedDocument(
        document_type="arrival_general_declaration",
        vessel_name=field("EVER EXAMPLE"),
        imo_number=field("1111111"),
        call_sign=field("9V1234"),
    )

    port_call = PortCall(
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        phase="arrival",
    )

    result = run_compliance_check(
        port_call,
        [registry, arrival],
    )

    assert result.status == "CORRECTION_REQUIRED"
    
def test_escalation_correction_required():

    result = determine_escalation(
        compliance_status="CORRECTION_REQUIRED",
    )

    assert result["action"] == "CORRECTION_REQUIRED"


def test_escalation_human_review():

    result = determine_escalation(
        compliance_status="HUMAN_REVIEW",
    )

    assert result["action"] == "HUMAN_REVIEW"


def test_escalation_physical_inspection():

    result = determine_escalation(
        compliance_status="PASS",
        physical_inspection_required=True,
    )

    assert result["action"] == "INSPECTION_REQUIRED"


def test_escalation_no_escalation():

    result = determine_escalation(
        compliance_status="PASS",
        physical_inspection_required=False,
    )

    assert result["action"] == "NO_ESCALATION"