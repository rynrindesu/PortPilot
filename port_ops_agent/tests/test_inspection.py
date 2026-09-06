from PortPilot.compliance.port_call import (
    PortCall,
)

from PortPilot.compliance.inspection import (
    determine_inspection_decision,
)


def create_port_call(
    *,
    carrying_dangerous_goods=False,
    radioactive_material=False,
):
    return PortCall(
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase="arrival",
        carrying_dangerous_goods=(
            carrying_dangerous_goods
        ),
        radioactive_material=(
            radioactive_material
        ),
    )


def test_low_risk_no_inspection():

    port_call = create_port_call()

    result = determine_inspection_decision(
        port_call,
        risk_level="low",
        compliance_status="PASS",
    )

    assert result["decision"] == "no_inspection"


def test_medium_risk_human_review():

    port_call = create_port_call()

    result = determine_inspection_decision(
        port_call,
        risk_level="medium",
        compliance_status="PASS",
    )

    assert result["decision"] == "human_review"


def test_high_risk_physical_inspection():

    port_call = create_port_call()

    result = determine_inspection_decision(
        port_call,
        risk_level="high",
        compliance_status="PASS",
    )

    assert result["decision"] == "inspection_required"


def test_correction_required_human_review():

    port_call = create_port_call()

    result = determine_inspection_decision(
        port_call,
        risk_level="low",
        compliance_status="CORRECTION_REQUIRED",
    )

    assert result["decision"] == "human_review"


def test_dangerous_goods_medium_risk():

    port_call = create_port_call(
        carrying_dangerous_goods=True,
    )

    result = determine_inspection_decision(
        port_call,
        risk_level="medium",
        compliance_status="PASS",
    )

    assert result["decision"] == "human_review"


def test_radioactive_material_requires_inspection():

    port_call = create_port_call(
        radioactive_material=True,
    )

    result = determine_inspection_decision(
        port_call,
        risk_level="medium",
        compliance_status="PASS",
    )

    assert result["decision"] == "inspection_required"