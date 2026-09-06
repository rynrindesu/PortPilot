from PortPilot.compliance.result import (
    ComplianceIssue,
)


REQUIRED_FIELDS = {
    "arrival_general_declaration": [
        "vessel_name",
        "imo_number",
        "call_sign",
        "gross_tonnage",
        "flag",
        "vessel_type",
        "port_of_registry",
        "official_number",
        "purpose_of_call",
        "arrival_date_time",
        "last_port",
        "master",
        "crew",
        "passengers",
        "total_cargo",
    ],

    "departure_general_declaration": [
        "vessel_name",
        "imo_number",
        "call_sign",
        "gross_tonnage",
        "flag",
        "vessel_type",
        "port_of_registry",
        "official_number",
        "purpose_of_call",
        "departure_date_time",
        "next_port",
        "master",
        "crew",
        "passengers",
        "total_cargo",
    ],

    "certificate_of_registry": [
        "vessel_name",
        "imo_number",
        "call_sign",
        "flag",
    ],

    "tonnage_certificate": [
        "vessel_name",
        "imo_number",
        "gross_tonnage",
    ],
}


def check_required_fields(document):
    """
    Check whether all required fields for a document
    are present.
    """

    issues = []

    required_fields = REQUIRED_FIELDS.get(
        document.document_type,
        [],
    )

    for field_name in required_fields:

        field = getattr(
            document,
            field_name,
            None,
        )

        if field is None or field.value is None:
            issues.append(
                ComplianceIssue(
                    code="MISSING_REQUIRED_FIELD",
                    message=(
                        f"Required field "
                        f"'{field_name}' is missing."
                    ),
                    severity="ERROR",
                    document_type=document.document_type,
                    field=field_name,
                )
            )

    return issues