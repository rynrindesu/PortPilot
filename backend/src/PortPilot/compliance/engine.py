from PortPilot.compliance.consistency import (
    check_document_consistency,
)

from PortPilot.compliance.fields import (
    check_required_fields,
)

from PortPilot.compliance.requirements import (
    get_required_documents,
    check_required_documents,
)

from PortPilot.compliance.rules import (
    evaluate_conditional_rules,
)

from PortPilot.compliance.result import (
    ComplianceResult,
)

from PortPilot.compliance.port_call import (
    PortCall,
)


def run_compliance_check(
    port_call: PortCall,
    documents: list,
) -> ComplianceResult:

    issues = []

    # --------------------------------
    # 1. Required documents
    # --------------------------------

    required_documents = get_required_documents(
        phase=port_call.phase,
        first_singapore_call=(
            port_call.first_singapore_call
        ),
        carrying_dangerous_goods=(
            port_call.carrying_dangerous_goods
        ),
    )

    issues.extend(
        check_required_documents(
            documents,
            required_documents,
        )
    )

    # --------------------------------
    # 2. Required fields
    # --------------------------------

    for document in documents:

        issues.extend(
            check_required_fields(document)
        )

    # --------------------------------
    # 3. Cross-document consistency
    # --------------------------------

    consistency_result = (
        check_document_consistency(documents)
    )

    issues.extend(
        consistency_result.issues
    )

    # --------------------------------
    # 4. Conditional rules
    # --------------------------------

    issues.extend(
        evaluate_conditional_rules(
            purpose_of_call=port_call.purpose_of_call,
            carrying_dangerous_goods=(
                port_call.carrying_dangerous_goods
            ),
            radioactive_material=(
                port_call.radioactive_material
            ),
        )
    )

    # --------------------------------
    # 5. Determine overall result
    # --------------------------------

    if any(
        issue.severity == "ERROR"
        for issue in issues
    ):
        status = "CORRECTION_REQUIRED"

    elif any(
        issue.severity == "WARNING"
        for issue in issues
    ):
        status = "HUMAN_REVIEW"

    else:
        status = "PASS"

    return ComplianceResult(
        status=status,
        issues=issues,
    )