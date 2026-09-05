import pytest

from pydantic import ValidationError

from PortPilot.agent.llm import (
    MockLLMProvider,
    LLMResponse,
)

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

    assert result.provider == "mock"

    assert (
        "physical inspection"
        in result.explanation.lower()
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

    assert result.provider == "mock"

    assert (
        "proceed"
        in result.explanation.lower()
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

    assert result.provider == "mock"

    assert (
        "correct"
        in result.explanation.lower()
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

    assert result.provider == "mock"

    assert (
        "human review"
        in result.explanation.lower()
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

    assert result.provider == "mock"

    assert (
        "physical inspection"
        in result.explanation.lower()
    )


def test_llm_response_rejects_authoritative_fields():
    with pytest.raises(ValidationError):
        LLMResponse(
            provider="malicious",
            explanation=(
                "The vessel should proceed."
            ),
            agent_action="PROCEED",
        )


def test_llm_response_accepts_safe_output():
    response = LLMResponse(
        provider="mock",
        explanation=(
            "Human inspection is required."
        ),
    )

    assert response.provider == "mock"

    assert (
        response.explanation
        == "Human inspection is required."
    )