from enum import Enum

from PortPilot.compliance.port_call import PortCall


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def calculate_risk_score(
    port_call: PortCall,
    *,
    compliance_status: str,
    document_inconsistency: bool = False,
):
    """
    Calculate a simple explainable risk score.

    The score is rule-based and intentionally deterministic.

    Returns:
        dict containing:
            - risk_score
            - risk_level
            - risk_factors
    """

    score = 0
    risk_factors = []

    # --------------------------------------------
    # Compliance status
    # --------------------------------------------

    if compliance_status == "CORRECTION_REQUIRED":
        score += 30

        risk_factors.append(
            "Compliance issues detected."
        )

    elif compliance_status == "HUMAN_REVIEW":
        score += 20

        risk_factors.append(
            "Human compliance review required."
        )

    # --------------------------------------------
    # Dangerous goods
    # --------------------------------------------

    if port_call.carrying_dangerous_goods:
        score += 25

        risk_factors.append(
            "Dangerous goods declared."
        )

    # --------------------------------------------
    # Radioactive material
    # --------------------------------------------

    if port_call.radioactive_material:
        score += 40

        risk_factors.append(
            "Radioactive material declared."
        )

    # --------------------------------------------
    # First Singapore call
    # --------------------------------------------

    if port_call.first_singapore_call:
        score += 10

        risk_factors.append(
            "First Singapore port call."
        )

    # --------------------------------------------
    # Document inconsistency
    # --------------------------------------------

    if document_inconsistency:
        score += 30

        risk_factors.append(
            "Inconsistencies detected across documents."
        )

    # --------------------------------------------
    # Determine risk level
    # --------------------------------------------

    if score >= 60:
        risk_level = RiskLevel.HIGH

    elif score >= 30:
        risk_level = RiskLevel.MEDIUM

    else:
        risk_level = RiskLevel.LOW

    return {
        "risk_score": score,
        "risk_level": risk_level.value,
        "risk_factors": risk_factors,
    }