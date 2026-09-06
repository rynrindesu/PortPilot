from PortPilot.compliance.port_call import (
    PortCall,
)

from PortPilot.compliance.risk import (
    calculate_risk_score,
)


def test_low_risk_port_call():

    port_call = PortCall(
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase="arrival",
        first_singapore_call=False,
        carrying_dangerous_goods=False,
        radioactive_material=False,
    )

    result = calculate_risk_score(
        port_call,
        compliance_status="PASS",
    )

    assert result["risk_score"] == 0
    assert result["risk_level"] == "low"
    assert result["risk_factors"] == []


def test_dangerous_goods_risk():

    port_call = PortCall(
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase="arrival",
        carrying_dangerous_goods=True,
    )

    result = calculate_risk_score(
        port_call,
        compliance_status="PASS",
    )

    assert result["risk_score"] == 25
    assert result["risk_level"] == "low"


def test_first_singapore_call_with_dg():

    port_call = PortCall(
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase="arrival",
        first_singapore_call=True,
        carrying_dangerous_goods=True,
    )

    result = calculate_risk_score(
        port_call,
        compliance_status="PASS",
    )

    assert result["risk_score"] == 35
    assert result["risk_level"] == "medium"


def test_radioactive_material():

    port_call = PortCall(
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase="arrival",
        radioactive_material=True,
    )

    result = calculate_risk_score(
        port_call,
        compliance_status="PASS",
    )

    assert result["risk_score"] == 40
    assert result["risk_level"] == "medium"


def test_high_risk_document_inconsistency():

    port_call = PortCall(
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase="arrival",
    )

    result = calculate_risk_score(
        port_call,
        compliance_status="PASS",
        document_inconsistency=True,
    )

    assert result["risk_score"] == 30
    assert result["risk_level"] == "medium"


def test_high_risk_combination():

    port_call = PortCall(
        vessel_name="EVER EXAMPLE",
        imo_number="9876543",
        call_sign="9V1234",
        phase="arrival",
        carrying_dangerous_goods=True,
        radioactive_material=True,
        first_singapore_call=True,
    )

    result = calculate_risk_score(
        port_call,
        compliance_status="PASS",
        document_inconsistency=True,
    )

    assert result["risk_score"] == 105
    assert result["risk_level"] == "high"