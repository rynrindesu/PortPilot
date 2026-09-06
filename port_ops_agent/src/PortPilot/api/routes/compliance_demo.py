from fastapi import APIRouter

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


router = APIRouter(
    prefix="/compliance-demo",
    tags=["Compliance Demo"],
)


def field(value):
    return ExtractedField(
        value=value,
        confidence=0.95,
        source_text=str(value),
    )


# =========================================================
# TEST 1 — Matching Documents
# =========================================================

@router.get("/matching-documents")
def matching_documents():

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

    return {
        "test": "matching_documents",
        "status": result.status,
        "issues": [
            issue.model_dump()
            for issue in result.issues
        ],
    }


# =========================================================
# TEST 2 — Call Sign Mismatch
# =========================================================

@router.get("/call-sign-mismatch")
def call_sign_mismatch():

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

    return {
        "test": "call_sign_mismatch",
        "status": result.status,
        "issues": [
            issue.model_dump()
            for issue in result.issues
        ],
    }


# =========================================================
# TEST 3 — Compliant Arrival
# =========================================================

@router.get("/compliant-arrival")
def compliant_arrival():

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

    return {
        "test": "compliant_arrival",
        "status": result.status,
        "issues": [
            issue.model_dump()
            for issue in result.issues
        ],
    }


# =========================================================
# TEST 4 — Missing Required Document
# =========================================================

@router.get("/missing-required-document")
def missing_required_document():

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

    return {
        "test": "missing_required_document",
        "status": result.status,
        "issues": [
            issue.model_dump()
            for issue in result.issues
        ],
    }


# =========================================================
# TEST 5 — Inconsistent IMO
# =========================================================

@router.get("/inconsistent-imo")
def inconsistent_imo():

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

    return {
        "test": "inconsistent_imo",
        "status": result.status,
        "issues": [
            issue.model_dump()
            for issue in result.issues
        ],
    }


# =========================================================
# TEST 6 — Escalation: Correction Required
# =========================================================

@router.get("/escalation/correction-required")
def escalation_correction_required():

    result = determine_escalation(
        compliance_status="CORRECTION_REQUIRED",
    )

    return {
        "test": "escalation_correction_required",
        **result,
    }


# =========================================================
# TEST 7 — Escalation: Human Review
# =========================================================

@router.get("/escalation/human-review")
def escalation_human_review():

    result = determine_escalation(
        compliance_status="HUMAN_REVIEW",
    )

    return {
        "test": "escalation_human_review",
        **result,
    }


# =========================================================
# TEST 8 — Escalation: Physical Inspection
# =========================================================

@router.get("/escalation/physical-inspection")
def escalation_physical_inspection():

    result = determine_escalation(
        compliance_status="PASS",
        physical_inspection_required=True,
    )

    return {
        "test": "escalation_physical_inspection",
        **result,
    }


# =========================================================
# TEST 9 — Escalation: No Escalation
# =========================================================

@router.get("/escalation/no-escalation")
def escalation_no_escalation():

    result = determine_escalation(
        compliance_status="PASS",
        physical_inspection_required=False,
    )

    return {
        "test": "escalation_no_escalation",
        **result,
    }