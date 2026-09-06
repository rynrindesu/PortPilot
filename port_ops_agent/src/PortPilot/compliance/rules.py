from PortPilot.compliance.result import (
    ComplianceIssue,
)


def evaluate_conditional_rules(
    *,
    purpose_of_call=None,
    carrying_dangerous_goods=False,
    radioactive_material=False,
):
    """
    Evaluate conditional compliance requirements.
    """

    issues = []

    if carrying_dangerous_goods:

        issues.append(
            ComplianceIssue(
                code="DG_DOCUMENT_REQUIRED",
                message=(
                    "Dangerous goods are declared. "
                    "Dangerous Goods documentation "
                    "must be verified."
                ),
                severity="WARNING",
                document_type="dangerous_goods_declaration",
            )
        )

    if radioactive_material:

        issues.append(
            ComplianceIssue(
                code="RADIOACTIVE_CARGO_REVIEW",
                message=(
                    "Radioactive material declared. "
                    "Additional regulatory approval "
                    "may be required."
                ),
                severity="WARNING",
            )
        )

    return issues