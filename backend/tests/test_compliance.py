from PortPilot.models.documents import (
    ExtractedDocument,
    ExtractedField,
)

from PortPilot.compliance.consistency import (
    check_document_consistency,
)


def create_field(value):
    return ExtractedField(
        value=value,
        confidence=0.95,
        source_text=str(value),
    )


def test_matching_documents():

    registry = ExtractedDocument(
        document_type="certificate_of_registry",
        vessel_name=create_field("EVER EXAMPLE"),
        imo_number=create_field("9876543"),
        call_sign=create_field("9V1234"),
        flag=create_field("Singapore"),
    )

    declaration = ExtractedDocument(
        document_type="arrival_general_declaration",
        vessel_name=create_field("EVER EXAMPLE"),
        imo_number=create_field("9876543"),
        call_sign=create_field("9V1234"),
        flag=create_field("Singapore"),
    )

    result = check_document_consistency(
        [registry, declaration]
    )

    assert result.status == "PASS"
    assert result.issues == []


def test_call_sign_mismatch():

    registry = ExtractedDocument(
        document_type="certificate_of_registry",
        vessel_name=create_field("EVER EXAMPLE"),
        imo_number=create_field("9876543"),
        call_sign=create_field("9V1234"),
    )

    declaration = ExtractedDocument(
        document_type="arrival_general_declaration",
        vessel_name=create_field("EVER EXAMPLE"),
        imo_number=create_field("9876543"),
        call_sign=create_field("9V5678"),
    )

    result = check_document_consistency(
        [registry, declaration]
    )

    assert result.status == "CORRECTION_REQUIRED"

    assert any(
        issue.field == "call_sign"
        for issue in result.issues
    )