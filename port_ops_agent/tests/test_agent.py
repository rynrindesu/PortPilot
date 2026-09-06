from PortPilot.models.documents import (
    ExtractedDocument,
    ExtractedField,
)

from PortPilot.workflow.state import (
    PortCallPhase,
    PortCallState,
    PortCallStatus,
)

from PortPilot.agent.agent import (
    run_port_call_agent,
    agent_advance_port_call,
)

from PortPilot.agent.graph import (
    run_agent_graph,
    run_inspection_start,
    run_inspection_completion,
)


def build_arrival_document(
    *,
    vessel_name: str = "EVER AGENT",
    imo_number: str = "9876560",
    call_sign: str = "9V7000",
):
    """
    Build a complete Arrival General Declaration
    for agent integration tests.
    """

    return ExtractedDocument(
        document_type="arrival_general_declaration",

        vessel_name=ExtractedField(
            value=vessel_name,
            confidence=0.99,
            source_text=vessel_name,
        ),

        imo_number=ExtractedField(
            value=imo_number,
            confidence=0.99,
            source_text=imo_number,
        ),

        call_sign=ExtractedField(
            value=call_sign,
            confidence=0.99,
            source_text=call_sign,
        ),

        gross_tonnage=ExtractedField(
            value=50000,
            confidence=0.99,
            source_text="50000",
        ),

        flag=ExtractedField(
            value="Singapore",
            confidence=0.99,
            source_text="Singapore",
        ),

        vessel_type=ExtractedField(
            value="Container Ship",
            confidence=0.99,
            source_text="Container Ship",
        ),

        port_of_registry=ExtractedField(
            value="Singapore",
            confidence=0.99,
            source_text="Singapore",
        ),

        official_number=ExtractedField(
            value="123460",
            confidence=0.99,
            source_text="123460",
        ),

        purpose_of_call=ExtractedField(
            value="cargo",
            confidence=0.99,
            source_text="cargo",
        ),

        arrival_date_time=ExtractedField(
            value="2026-09-05T08:00:00",
            confidence=0.99,
            source_text="2026-09-05T08:00:00",
        ),

        last_port=ExtractedField(
            value="Port Klang",
            confidence=0.99,
            source_text="Port Klang",
        ),

        master=ExtractedField(
            value="John Tan",
            confidence=0.99,
            source_text="John Tan",
        ),

        crew=ExtractedField(
            value=20,
            confidence=0.99,
            source_text="20",
        ),

        passengers=ExtractedField(
            value=0,
            confidence=0.99,
            source_text="0",
        ),

        total_cargo=ExtractedField(
            value="45000 MT",
            confidence=0.99,
            source_text="45000 MT",
        ),
    )


def test_agent_proceeds_for_clean_low_risk_port_call():
    """
    A clean arrival should produce PROCEED.
    """

    state = PortCallState(
        port_call_id="PC-AGENT-001",
        vessel_name="EVER AGENT",
        imo_number="9876560",
        call_sign="9V7000",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,
        purpose_of_call="cargo",
        carrying_dangerous_goods=False,
        radioactive_material=False,
    )

    state.documents = [
        build_arrival_document()
    ]

    result = run_port_call_agent(state)

    assert result["agent_action"] == "PROCEED"

    assert (
        result["compliance_status"]
        == "PASS"
    )

    assert result["risk_level"] == "low"

    assert (
        result["inspection_decision"]
        == "no_inspection"
    )

    assert (
        result["escalation"]
        == "NO_ESCALATION"
    )


def test_agent_requests_correction_when_document_missing():
    """
    Missing required documents should produce
    REQUEST_CORRECTION.
    """

    state = PortCallState(
        port_call_id="PC-AGENT-002",
        vessel_name="EVER MISSING",
        imo_number="9876561",
        call_sign="9V7001",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,
        purpose_of_call="cargo",
    )

    result = run_port_call_agent(state)

    assert (
        result["agent_action"]
        == "REQUEST_CORRECTION"
    )

    assert (
        result["compliance_status"]
        == "CORRECTION_REQUIRED"
    )

    assert (
        result["escalation"]
        == "CORRECTION_REQUIRED"
    )

    assert (
        state.status
        == PortCallStatus.CORRECTION_REQUIRED
    )


def test_agent_requests_inspection_for_high_risk_port_call():
    """
    Radioactive material should create the
    current high-risk inspection path.
    """

    state = PortCallState(
        port_call_id="PC-AGENT-003",
        vessel_name="EVER HIGH RISK",
        imo_number="9876562",
        call_sign="9V7002",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,
        purpose_of_call="cargo",
        carrying_dangerous_goods=False,
        radioactive_material=True,
    )

    state.documents = [
        build_arrival_document(
            vessel_name="EVER HIGH RISK",
            imo_number="9876562",
            call_sign="9V7002",
        )
    ]

    result = run_port_call_agent(state)

    assert (
        result["agent_action"]
        == "REQUEST_INSPECTION"
    )

    assert (
        result["compliance_status"]
        == "HUMAN_REVIEW"
    )

    assert result["risk_level"] == "high"

    assert (
        result["inspection_decision"]
        == "inspection_required"
    )

    assert (
        result["escalation"]
        == "INSPECTION_REQUIRED"
    )

    assert (
        state.status
        == PortCallStatus.INSPECTION_REQUIRED
    )


def test_agent_graph_advances_clean_arrival():
    """
    A clean arrival should be automatically advanced
    by the graph to operations.
    """

    state = PortCallState(
        port_call_id="PC-GRAPH-001",
        vessel_name="EVER GRAPH",
        imo_number="9876563",
        call_sign="9V7003",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,
        purpose_of_call="cargo",
    )

    state.documents = [
        build_arrival_document(
            vessel_name="EVER GRAPH",
            imo_number="9876563",
            call_sign="9V7003",
        )
    ]

    result = run_agent_graph(state)

    assert (
        result["graph_status"]
        == "ADVANCED"
    )

    assert result["next_step"] == "advance"

    assert (
        state.phase
        == PortCallPhase.OPERATIONS
    )

    assert (
        state.status
        == PortCallStatus.OPERATIONS
    )


def test_agent_graph_waits_for_inspection():
    """
    High-risk cases should stop and wait
    for human physical inspection.
    """

    state = PortCallState(
        port_call_id="PC-GRAPH-002",
        vessel_name="EVER GRAPH HIGH",
        imo_number="9876564",
        call_sign="9V7004",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,
        purpose_of_call="cargo",
        radioactive_material=True,
    )

    state.documents = [
        build_arrival_document(
            vessel_name="EVER GRAPH HIGH",
            imo_number="9876564",
            call_sign="9V7004",
        )
    ]

    result = run_agent_graph(state)

    assert (
        result["graph_status"]
        == "WAITING_FOR_INSPECTION"
    )

    assert (
        result["next_step"]
        == "inspection_required"
    )

    assert (
        state.status
        == PortCallStatus.INSPECTION_REQUIRED
    )


def test_agent_graph_full_inspection_clearance_flow():
    """
    Full agent inspection path:

    agent graph
        ->
    waiting for inspection
        ->
    inspection start
        ->
    human clears
        ->
    advance
    """

    state = PortCallState(
        port_call_id="PC-GRAPH-003",
        vessel_name="EVER HUMAN",
        imo_number="9876565",
        call_sign="9V7005",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,
        purpose_of_call="cargo",
        radioactive_material=True,
    )

    state.documents = [
        build_arrival_document(
            vessel_name="EVER HUMAN",
            imo_number="9876565",
            call_sign="9V7005",
        )
    ]

    # --------------------------------------------
    # Agent detects inspection requirement
    # --------------------------------------------

    graph_result = run_agent_graph(state)

    assert (
        graph_result["graph_status"]
        == "WAITING_FOR_INSPECTION"
    )

    # --------------------------------------------
    # Human inspection starts
    # --------------------------------------------

    start_result = run_inspection_start(
        state
    )

    assert (
        start_result["graph_status"]
        == "INSPECTION_IN_PROGRESS"
    )

    assert (
        state.status
        == PortCallStatus.INSPECTION_IN_PROGRESS
    )

    # --------------------------------------------
    # Human clears inspection
    # --------------------------------------------

    completion_result = (
        run_inspection_completion(
            state,
            cleared=True,
            findings=(
                "Cargo physically verified."
            ),
        )
    )

    assert (
        completion_result["graph_status"]
        == "INSPECTION_CLEARED"
    )

    assert (
        state.status
        == PortCallStatus.INSPECTION_CLEARED
    )

    # --------------------------------------------
    # Advance after human clearance
    # --------------------------------------------

    advance_result = (
        agent_advance_port_call(state)
    )

    assert advance_result["success"] is True

    assert (
        state.phase
        == PortCallPhase.OPERATIONS
    )

    assert (
        state.status
        == PortCallStatus.OPERATIONS
    )


def test_agent_graph_rejected_inspection_does_not_advance():
    """
    If the human inspector rejects the physical
    inspection, the port call must remain blocked.
    """

    state = PortCallState(
        port_call_id="PC-GRAPH-004",
        vessel_name="EVER REJECT AGENT",
        imo_number="9876566",
        call_sign="9V7006",
        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,
        purpose_of_call="cargo",
        radioactive_material=True,
    )

    state.documents = [
        build_arrival_document(
            vessel_name="EVER REJECT AGENT",
            imo_number="9876566",
            call_sign="9V7006",
        )
    ]

    graph_result = run_agent_graph(state)

    assert (
        graph_result["graph_status"]
        == "WAITING_FOR_INSPECTION"
    )

    start_result = run_inspection_start(
        state
    )

    assert (
        start_result["graph_status"]
        == "INSPECTION_IN_PROGRESS"
    )

    completion_result = (
        run_inspection_completion(
            state,
            cleared=False,
            findings=(
                "Declared cargo does not match "
                "physical inspection."
            ),
        )
    )

    assert (
        completion_result["graph_status"]
        == "INSPECTION_REJECTED"
    )

    assert (
        state.status
        == PortCallStatus.INSPECTION_REJECTED
    )

    advance_result = (
        agent_advance_port_call(state)
    )

    assert advance_result["success"] is False

    assert (
        state.phase
        == PortCallPhase.ARRIVAL
    )

    assert (
        state.status
        == PortCallStatus.INSPECTION_REJECTED
    )