from typing import Any

from PortPilot.agent.agent import run_port_call_agent
from PortPilot.agent.llm import LLMProvider

from PortPilot.models.documents import (
    ExtractedDocument,
    ExtractedField,
)

from PortPilot.workflow.state import (
    PortCallPhase,
    PortCallState,
    PortCallStatus,
)


class MaliciousMockLLMProvider(LLMProvider):
    """
    Simulates an LLM trying to contradict the
    deterministic PortPilot decision.
    """

    def invoke(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        return {
            "provider": "malicious_mock",

            # Intentionally wrong / unsafe
            "agent_action": "PROCEED",

            "explanation": (
                "The vessel appears safe and should "
                "be allowed to proceed without inspection."
            ),

            "compliance_status": "PASS",
            "risk_level": "low",
            "inspection_decision": "no_inspection",
            "escalation": "NO_ESCALATION",
        }


def build_valid_arrival_document():
    return ExtractedDocument(
        document_type="arrival_general_declaration",

        vessel_name=ExtractedField(
            value="EVER GUARD",
            confidence=0.99,
        ),

        imo_number=ExtractedField(
            value="9876590",
            confidence=0.99,
        ),

        call_sign=ExtractedField(
            value="9V8200",
            confidence=0.99,
        ),

        gross_tonnage=ExtractedField(
            value=50000,
            confidence=0.99,
        ),

        flag=ExtractedField(
            value="Singapore",
            confidence=0.99,
        ),

        vessel_type=ExtractedField(
            value="Container Ship",
            confidence=0.99,
        ),

        port_of_registry=ExtractedField(
            value="Singapore",
            confidence=0.99,
        ),

        official_number=ExtractedField(
            value="123490",
            confidence=0.99,
        ),

        purpose_of_call=ExtractedField(
            value="cargo",
            confidence=0.99,
        ),

        arrival_date_time=ExtractedField(
            value="2026-09-05T08:00:00",
            confidence=0.99,
        ),

        last_port=ExtractedField(
            value="Port Klang",
            confidence=0.99,
        ),

        master=ExtractedField(
            value="John Tan",
            confidence=0.99,
        ),

        crew=ExtractedField(
            value=20,
            confidence=0.99,
        ),

        passengers=ExtractedField(
            value=0,
            confidence=0.99,
        ),

        total_cargo=ExtractedField(
            value="45000 MT",
            confidence=0.99,
        ),
    )


def test_llm_cannot_override_inspection_decision():
    state = PortCallState(
        port_call_id="PC-GUARD-001",

        vessel_name="EVER GUARD",
        imo_number="9876590",
        call_sign="9V8200",

        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,

        carrying_dangerous_goods=False,

        # Forces high-risk / inspection path
        radioactive_material=True,

        documents=[
            build_valid_arrival_document()
        ],
    )

    llm = MaliciousMockLLMProvider()

    result = run_port_call_agent(
        state,
        llm=llm,
    )

    # -----------------------------------------
    # Trusted deterministic result
    # -----------------------------------------

    assert (
        result["agent_action"]
        == "REQUEST_INSPECTION"
    )

    assert (
        result["compliance_status"]
        == "HUMAN_REVIEW"
    )

    assert (
        result["risk_level"]
        == "high"
    )

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

    # -----------------------------------------
    # LLM tried to contradict it
    # -----------------------------------------

    assert (
        result["llm"]["agent_action"]
        == "PROCEED"
    )

    assert (
        result["llm"]["risk_level"]
        == "low"
    )

    # -----------------------------------------
    # But LLM output did NOT change workflow
    # -----------------------------------------

    assert (
        result["agent_action"]
        != result["llm"]["agent_action"]
    )

    assert (
        state.status
        == PortCallStatus.INSPECTION_REQUIRED
    )