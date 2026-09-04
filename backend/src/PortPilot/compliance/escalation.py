from PortPilot.compliance.result import (
    ComplianceIssue,
)


def determine_escalation(
    *,
    compliance_status: str,
    physical_inspection_required: bool = False,
):
    """
    Determine whether the case needs human review
    or physical inspection.
    """

    if compliance_status == "CORRECTION_REQUIRED":
        return {
            "action": "CORRECTION_REQUIRED",
            "reason": (
                "One or more required compliance "
                "conditions have not been satisfied."
            ),
        }

    if physical_inspection_required:
        return {
            "action": "INSPECTION_REQUIRED",
            "reason": (
                "Document verification does not establish "
                "the physical identity or condition of cargo."
            ),
        }

    if compliance_status == "HUMAN_REVIEW":
        return {
            "action": "HUMAN_REVIEW",
            "reason": (
                "The case requires human assessment."
            ),
        }

    return {
        "action": "NO_ESCALATION",
        "reason": "No escalation required.",
    }