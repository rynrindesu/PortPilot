from PortPilot.compliance.result import (
    ComplianceIssue,
)


BASE_ARRIVAL_DOCUMENTS = {
    "arrival_general_declaration",
}


BASE_DEPARTURE_DOCUMENTS = {
    "departure_general_declaration",
}


def get_required_documents(
    phase: str,
    *,
    first_singapore_call: bool = False,
    carrying_dangerous_goods: bool = False,
):
    """
    Determine documents required for a port-call phase.

    This is intentionally rule-based.
    """

    required = set()

    if phase == "arrival":
        required.update(BASE_ARRIVAL_DOCUMENTS)

        if first_singapore_call:
            required.add("certificate_of_registry")
            required.add("tonnage_certificate")

        if carrying_dangerous_goods:
            required.add("dangerous_goods_declaration")

    elif phase == "departure":
        required.update(BASE_DEPARTURE_DOCUMENTS)

    return required


def check_required_documents(
    documents: list,
    required_documents: set,
):
    """
    Check whether all required document types
    are present.
    """

    present_types = {
        document.document_type
        for document in documents
    }

    issues = []

    for required in required_documents:

        if required not in present_types:

            issues.append(
                ComplianceIssue(
                    code="MISSING_REQUIRED_DOCUMENT",
                    message=(
                        f"Required document "
                        f"'{required}' is missing."
                    ),
                    severity="ERROR",
                    document_type=required,
                )
            )

    return issues