from PortPilot.compliance.result import (
    ComplianceIssue,
    ComplianceResult,
)


COMPARABLE_FIELDS = [
    "vessel_name",
    "imo_number",
    "call_sign",
    "flag",
]


def get_field_value(document, field_name: str):
    """
    Safely retrieve an extracted field's value.
    """

    field = getattr(document, field_name, None)

    if field is None:
        return None

    return field.value


def check_document_consistency(documents: list) -> ComplianceResult:
    """
    Compare common vessel-identifying fields across documents.
    """

    issues = []

    for field_name in COMPARABLE_FIELDS:

        values = {}

        for document in documents:

            value = get_field_value(
                document,
                field_name,
            )

            if value is not None:
                values.setdefault(
                    str(value).strip().lower(),
                    []
                ).append(document.document_type)

        # No conflict if zero or one unique value exists.
        if len(values) <= 1:
            continue

        issues.append(
            ComplianceIssue(
                code="FIELD_MISMATCH",
                message=(
                    f"Conflicting values found for "
                    f"{field_name}."
                ),
                severity="ERROR",
                field=field_name,
            )
        )

    if issues:
        return ComplianceResult(
            status="CORRECTION_REQUIRED",
            issues=issues,
        )

    return ComplianceResult(
        status="PASS",
        issues=[],
    )