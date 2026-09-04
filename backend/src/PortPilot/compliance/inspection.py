from enum import Enum

from PortPilot.compliance.port_call import PortCall
from PortPilot.compliance.risk import RiskLevel


class InspectionDecision(str, Enum):
    NO_INSPECTION = "no_inspection"
    HUMAN_REVIEW = "human_review"
    INSPECTION_REQUIRED = "inspection_required"


def determine_inspection_decision(
    port_call: PortCall,
    *,
    risk_level: str,
    compliance_status: str,
):
    """
    Determine whether human review or physical inspection
    is required.

    This decision is rule-based and explainable.
    """

    reasons = []

    # --------------------------------------------------
    # Compliance problems
    # --------------------------------------------------

    if compliance_status == "CORRECTION_REQUIRED":
        return {
            "decision": InspectionDecision.HUMAN_REVIEW.value,
            "reason": (
                "Compliance issues must be corrected "
                "before the port call can proceed."
            ),
            "reasons": [
                "Compliance correction required."
            ],
        }

    # --------------------------------------------------
    # High risk
    # --------------------------------------------------

    if risk_level == RiskLevel.HIGH.value:

        reasons.append(
            "Port call has been assessed as high risk."
        )

        return {
            "decision": (
                InspectionDecision.INSPECTION_REQUIRED.value
            ),
            "reason": (
                "High-risk port call requires "
                "physical inspection."
            ),
            "reasons": reasons,
        }

    # --------------------------------------------------
    # Dangerous goods
    # --------------------------------------------------

    if port_call.carrying_dangerous_goods:

        reasons.append(
            "Dangerous goods are declared."
        )

        if risk_level == RiskLevel.MEDIUM.value:

            return {
                "decision": (
                    InspectionDecision.HUMAN_REVIEW.value
                ),
                "reason": (
                    "Dangerous goods require "
                    "additional human assessment."
                ),
                "reasons": reasons,
            }

    # --------------------------------------------------
    # Radioactive material
    # --------------------------------------------------

    if port_call.radioactive_material:

        return {
            "decision": (
                InspectionDecision.INSPECTION_REQUIRED.value
            ),
            "reason": (
                "Radioactive material requires "
                "physical inspection and human assessment."
            ),
            "reasons": [
                "Radioactive material declared."
            ],
        }

    # --------------------------------------------------
    # Medium risk
    # --------------------------------------------------

    if risk_level == RiskLevel.MEDIUM.value:

        return {
            "decision": (
                InspectionDecision.HUMAN_REVIEW.value
            ),
            "reason": (
                "Medium-risk port call requires "
                "human assessment."
            ),
            "reasons": [
                "Port call has been assessed as medium risk."
            ],
        }

    # --------------------------------------------------
    # Low risk
    # --------------------------------------------------

    return {
        "decision": InspectionDecision.NO_INSPECTION.value,
        "reason": (
            "No additional inspection is required "
            "based on the available information."
        ),
        "reasons": [],
    }