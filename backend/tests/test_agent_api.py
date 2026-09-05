from fastapi.testclient import TestClient

from PortPilot.main import app
from PortPilot.api.routes.port_calls import PORT_CALLS


client = TestClient(app)


def clean_store():
    PORT_CALLS.clear()


def build_arrival_document(
    *,
    vessel_name: str,
    imo_number: str,
    call_sign: str,
):
    return [
        {
            "document_type": "arrival_general_declaration",

            "vessel_name": {
                "value": vessel_name,
                "confidence": 0.99,
                "source_text": vessel_name,
            },

            "imo_number": {
                "value": imo_number,
                "confidence": 0.99,
                "source_text": imo_number,
            },

            "call_sign": {
                "value": call_sign,
                "confidence": 0.99,
                "source_text": call_sign,
            },

            "gross_tonnage": {
                "value": 50000,
                "confidence": 0.99,
                "source_text": "50000",
            },

            "flag": {
                "value": "Singapore",
                "confidence": 0.99,
                "source_text": "Singapore",
            },

            "vessel_type": {
                "value": "Container Ship",
                "confidence": 0.99,
                "source_text": "Container Ship",
            },

            "port_of_registry": {
                "value": "Singapore",
                "confidence": 0.99,
                "source_text": "Singapore",
            },

            "official_number": {
                "value": "123480",
                "confidence": 0.99,
                "source_text": "123480",
            },

            "purpose_of_call": {
                "value": "cargo",
                "confidence": 0.99,
                "source_text": "cargo",
            },

            "arrival_date_time": {
                "value": "2026-09-05T08:00:00",
                "confidence": 0.99,
                "source_text": "2026-09-05T08:00:00",
            },

            "last_port": {
                "value": "Port Klang",
                "confidence": 0.99,
                "source_text": "Port Klang",
            },

            "master": {
                "value": "John Tan",
                "confidence": 0.99,
                "source_text": "John Tan",
            },

            "crew": {
                "value": 20,
                "confidence": 0.99,
                "source_text": "20",
            },

            "passengers": {
                "value": 0,
                "confidence": 0.99,
                "source_text": "0",
            },

            "total_cargo": {
                "value": "45000 MT",
                "confidence": 0.99,
                "source_text": "45000 MT",
            },
        }
    ]


def test_agent_api_clean_vessel_advances_to_operations():
    """
    Full API path:

    create port call
        ->
    submit valid arrival document
        ->
    run agent
        ->
    PASS / LOW
        ->
    automatically advance to operations
    """

    clean_store()

    port_call_id = "PC-AGENT-API-TEST-001"

    # --------------------------------------------
    # Step 1 — Create port call
    # --------------------------------------------

    response = client.post(
        "/port-calls",
        json={
            "port_call_id": port_call_id,
            "vessel_name": "EVER API CLEAN",
            "imo_number": "9876580",
            "call_sign": "9V8100",
            "first_singapore_call": False,
            "purpose_of_call": "cargo",
            "carrying_dangerous_goods": False,
            "radioactive_material": False,
        },
    )

    assert response.status_code == 200

    created = response.json()

    assert created["phase"] == "arrival"
    assert created["status"] == "arrival_pending"

    assert (
        created["events"][0]["event"]
        == "PORT_CALL_CREATED"
    )

    # --------------------------------------------
    # Step 2 — Submit arrival declaration
    # --------------------------------------------

    response = client.post(
        f"/port-calls/{port_call_id}/documents",
        json=build_arrival_document(
            vessel_name="EVER API CLEAN",
            imo_number="9876580",
            call_sign="9V8100",
        ),
    )

    assert response.status_code == 200

    document_result = response.json()

    assert document_result["success"] is True
    assert document_result["document_count"] == 1

    # --------------------------------------------
    # Step 3 — Run agent
    # --------------------------------------------

    response = client.post(
        f"/agent/port-calls/{port_call_id}/run"
    )

    assert response.status_code == 200

    result = response.json()["result"]

    assert (
        result["graph_status"]
        == "ADVANCED"
    )

    assert (
        result["next_step"]
        == "advance"
    )

    assert (
        result["agent"]["agent_action"]
        == "PROCEED"
    )

    assert (
        result["agent"]["compliance_status"]
        == "PASS"
    )

    assert (
        result["agent"]["risk_level"]
        == "low"
    )

    assert (
        result["agent"]["inspection_decision"]
        == "no_inspection"
    )

    assert (
        result["agent"]["escalation"]
        == "NO_ESCALATION"
    )

    # --------------------------------------------
    # Step 4 — Verify stored port-call state
    # --------------------------------------------

    response = client.get(
        f"/port-calls/{port_call_id}"
    )

    assert response.status_code == 200

    state = response.json()

    assert state["phase"] == "operations"
    assert state["status"] == "operations"

    event_names = [
        event["event"]
        for event in state["events"]
    ]

    assert (
        "PORT_CALL_CREATED"
        in event_names
    )

    assert (
        "COMPLIANCE_CHECKED"
        in event_names
    )

    assert (
        "PORT_CALL_ADVANCED"
        in event_names
    )


def test_agent_api_high_risk_vessel_waits_for_inspection():
    """
    High-risk API path:

    create port call
        ->
    submit valid arrival document
        ->
    agent detects high risk
        ->
    stop at WAITING_FOR_INSPECTION
    """

    clean_store()

    port_call_id = "PC-AGENT-API-TEST-002"

    response = client.post(
        "/port-calls",
        json={
            "port_call_id": port_call_id,
            "vessel_name": "EVER API HIGH",
            "imo_number": "9876581",
            "call_sign": "9V8101",
            "first_singapore_call": False,
            "purpose_of_call": "cargo",
            "carrying_dangerous_goods": False,
            "radioactive_material": True,
        },
    )

    assert response.status_code == 200

    response = client.post(
        f"/port-calls/{port_call_id}/documents",
        json=build_arrival_document(
            vessel_name="EVER API HIGH",
            imo_number="9876581",
            call_sign="9V8101",
        ),
    )

    assert response.status_code == 200

    response = client.post(
        f"/agent/port-calls/{port_call_id}/run"
    )

    assert response.status_code == 200

    result = response.json()["result"]

    assert (
        result["graph_status"]
        == "WAITING_FOR_INSPECTION"
    )

    assert (
        result["next_step"]
        == "inspection_required"
    )

    assert (
        result["agent"]["agent_action"]
        == "REQUEST_INSPECTION"
    )

    assert (
        result["agent"]["compliance_status"]
        == "HUMAN_REVIEW"
    )

    assert (
        result["agent"]["risk_level"]
        == "high"
    )

    assert (
        result["agent"]["inspection_decision"]
        == "inspection_required"
    )

    assert (
        result["agent"]["escalation"]
        == "INSPECTION_REQUIRED"
    )

    response = client.get(
        f"/port-calls/{port_call_id}"
    )

    state = response.json()

    assert state["phase"] == "arrival"

    assert (
        state["status"]
        == "inspection_required"
    )

    event_names = [
        event["event"]
        for event in state["events"]
    ]

    assert (
        "COMPLIANCE_CHECKED"
        in event_names
    )

    assert (
        "PORT_CALL_ADVANCED"
        not in event_names
    )


def test_agent_api_full_human_inspection_clearance_flow():
    """
    Full human-in-the-loop API path:

    high risk
        ->
    waiting for inspection
        ->
    start inspection
        ->
    human clears
        ->
    advance to operations
    """

    clean_store()

    port_call_id = "PC-AGENT-API-TEST-003"

    # --------------------------------------------
    # Create high-risk port call
    # --------------------------------------------

    response = client.post(
        "/port-calls",
        json={
            "port_call_id": port_call_id,
            "vessel_name": "EVER API INSPECT",
            "imo_number": "9876582",
            "call_sign": "9V8102",
            "first_singapore_call": False,
            "purpose_of_call": "cargo",
            "carrying_dangerous_goods": False,
            "radioactive_material": True,
        },
    )

    assert response.status_code == 200

    # --------------------------------------------
    # Submit valid declaration
    # --------------------------------------------

    response = client.post(
        f"/port-calls/{port_call_id}/documents",
        json=build_arrival_document(
            vessel_name="EVER API INSPECT",
            imo_number="9876582",
            call_sign="9V8102",
        ),
    )

    assert response.status_code == 200

    # --------------------------------------------
    # Run agent
    # --------------------------------------------

    response = client.post(
        f"/agent/port-calls/{port_call_id}/run"
    )

    assert response.status_code == 200

    assert (
        response.json()["result"]["graph_status"]
        == "WAITING_FOR_INSPECTION"
    )

    # --------------------------------------------
    # Start human inspection
    # --------------------------------------------

    response = client.post(
        (
            f"/agent/port-calls/"
            f"{port_call_id}/inspection/start"
        )
    )

    assert response.status_code == 200

    result = response.json()["result"]

    assert (
        result["graph_status"]
        == "INSPECTION_IN_PROGRESS"
    )

    # --------------------------------------------
    # Human clears inspection
    # --------------------------------------------

    response = client.post(
        (
            f"/agent/port-calls/"
            f"{port_call_id}/inspection/complete"
        ),
        json={
            "cleared": True,
            "findings": (
                "Cargo physically verified "
                "with no discrepancies."
            ),
        },
    )

    assert response.status_code == 200

    result = response.json()["result"]

    assert (
        result["graph_status"]
        == "INSPECTION_CLEARED"
    )

    # --------------------------------------------
    # Advance port call
    # --------------------------------------------

    response = client.post(
        (
            f"/agent/port-calls/"
            f"{port_call_id}/advance"
        )
    )

    assert response.status_code == 200

    response_data = response.json()

    assert (
        response_data["result"]["success"]
        is True
    )

    assert (
        response_data["state"]["phase"]
        == "operations"
    )

    assert (
        response_data["state"]["status"]
        == "operations"
    )

    # --------------------------------------------
    # Verify audit history
    # --------------------------------------------

    response = client.get(
        f"/port-calls/{port_call_id}"
    )

    state = response.json()

    event_names = [
        event["event"]
        for event in state["events"]
    ]

    assert (
        "PORT_CALL_CREATED"
        in event_names
    )

    assert (
        "COMPLIANCE_CHECKED"
        in event_names
    )

    assert (
        "INSPECTION_STARTED"
        in event_names
    )

    assert (
        "INSPECTION_CLEARED"
        in event_names
    )

    assert (
        "PORT_CALL_ADVANCED"
        in event_names
    )


def test_agent_api_rejected_inspection_cannot_advance():
    """
    Rejected human inspection must block the
    agent API from advancing the vessel.
    """

    clean_store()

    port_call_id = "PC-AGENT-API-TEST-004"

    response = client.post(
        "/port-calls",
        json={
            "port_call_id": port_call_id,
            "vessel_name": "EVER API REJECT",
            "imo_number": "9876583",
            "call_sign": "9V8103",
            "first_singapore_call": False,
            "purpose_of_call": "cargo",
            "carrying_dangerous_goods": False,
            "radioactive_material": True,
        },
    )

    assert response.status_code == 200

    response = client.post(
        f"/port-calls/{port_call_id}/documents",
        json=build_arrival_document(
            vessel_name="EVER API REJECT",
            imo_number="9876583",
            call_sign="9V8103",
        ),
    )

    assert response.status_code == 200

    response = client.post(
        f"/agent/port-calls/{port_call_id}/run"
    )

    assert response.status_code == 200

    response = client.post(
        (
            f"/agent/port-calls/"
            f"{port_call_id}/inspection/start"
        )
    )

    assert response.status_code == 200

    response = client.post(
        (
            f"/agent/port-calls/"
            f"{port_call_id}/inspection/complete"
        ),
        json={
            "cleared": False,
            "findings": (
                "Physical cargo did not match "
                "the submitted declaration."
            ),
        },
    )

    assert response.status_code == 200

    assert (
        response.json()["result"]["graph_status"]
        == "INSPECTION_REJECTED"
    )

    # Advance must now be blocked
    response = client.post(
        (
            f"/agent/port-calls/"
            f"{port_call_id}/advance"
        )
    )

    assert response.status_code == 400

    # Verify state remains rejected
    response = client.get(
        f"/port-calls/{port_call_id}"
    )

    state = response.json()

    assert state["phase"] == "arrival"

    assert (
        state["status"]
        == "inspection_rejected"
    )

    event_names = [
        event["event"]
        for event in state["events"]
    ]

    assert (
        "INSPECTION_REJECTED"
        in event_names
    )

    assert (
        "PORT_CALL_ADVANCED"
        not in event_names
    )