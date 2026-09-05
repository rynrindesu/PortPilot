from PortPilot.agent.llm import MockLLMProvider

from PortPilot.agent.prompts import (
    PORTPILOT_SYSTEM_PROMPT,
    PORTPILOT_DECISION_PROMPT,
)

def test_mock_llm_request_inspection():
    llm = MockLLMProvider()

    result = llm.invoke(
        system_prompt=(
            "You are the PortPilot maritime assistant."
        ),
        user_prompt=(
            "Explain the current port-call decision."
        ),
        context={
            "agent_action": "REQUEST_INSPECTION",
            "compliance_status": "HUMAN_REVIEW",
            "risk_level": "high",
            "inspection_decision": "inspection_required",
            "escalation": "INSPECTION_REQUIRED",
        },
    )

    assert result["provider"] == "mock"

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
        "physical inspection"
        in result["explanation"].lower()
    )
    
def test_mock_llm_proceed():
    llm = MockLLMProvider()

    result = llm.invoke(
        system_prompt="PortPilot assistant.",
        user_prompt="Explain the decision.",
        context={
            "agent_action": "PROCEED",
            "compliance_status": "PASS",
            "risk_level": "low",
            "inspection_decision": "no_inspection",
            "escalation": "NO_ESCALATION",
        },
    )

    assert result["agent_action"] == "PROCEED"
    assert result["compliance_status"] == "PASS"
    assert result["risk_level"] == "low"

    assert (
        "proceed"
        in result["explanation"].lower()
    )


def test_mock_llm_request_correction():
    llm = MockLLMProvider()

    result = llm.invoke(
        system_prompt="PortPilot assistant.",
        user_prompt="Explain the decision.",
        context={
            "agent_action": "REQUEST_CORRECTION",
            "compliance_status": "CORRECTION_REQUIRED",
            "risk_level": "medium",
            "inspection_decision": "human_review",
            "escalation": "CORRECTION_REQUIRED",
        },
    )

    assert (
        result["agent_action"]
        == "REQUEST_CORRECTION"
    )

    assert (
        "correct"
        in result["explanation"].lower()
    )


def test_mock_llm_request_human_review():
    llm = MockLLMProvider()

    result = llm.invoke(
        system_prompt="PortPilot assistant.",
        user_prompt="Explain the decision.",
        context={
            "agent_action": "REQUEST_HUMAN_REVIEW",
            "compliance_status": "HUMAN_REVIEW",
            "risk_level": "medium",
            "inspection_decision": "human_review",
            "escalation": "HUMAN_REVIEW",
        },
    )

    assert (
        result["agent_action"]
        == "REQUEST_HUMAN_REVIEW"
    )

    assert (
        "human review"
        in result["explanation"].lower()
    )
    
def test_mock_llm_with_portpilot_prompts():
    llm = MockLLMProvider()

    result = llm.invoke(
        system_prompt=PORTPILOT_SYSTEM_PROMPT,
        user_prompt=PORTPILOT_DECISION_PROMPT,
        context={
            "agent_action": "REQUEST_INSPECTION",
            "compliance_status": "HUMAN_REVIEW",
            "risk_level": "high",
            "inspection_decision": "inspection_required",
            "escalation": "INSPECTION_REQUIRED",
        },
    )

    assert result["provider"] == "mock"

    assert (
        result["agent_action"]
        == "REQUEST_INSPECTION"
    )

    assert (
        "physical inspection"
        in result["explanation"].lower()
    )