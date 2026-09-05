from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """
    Provider-neutral interface for PortPilot LLMs.

    The rest of the agent should depend on this
    interface instead of depending directly on
    Bedrock, OpenAI, or any other provider.
    """

    @abstractmethod
    def invoke(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Invoke the language model.

        Returns a structured dictionary rather than
        unstructured free-form text.
        """
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """
    Local deterministic mock LLM.

    This lets us develop and test the agent without
    requiring AWS Bedrock access.
    """

    def invoke(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        context = context or {}

        agent_action = context.get(
            "agent_action",
            "UNKNOWN",
        )

        compliance_status = context.get(
            "compliance_status",
            "UNKNOWN",
        )

        risk_level = context.get(
            "risk_level",
            "unknown",
        )

        inspection_decision = context.get(
            "inspection_decision",
            "unknown",
        )

        escalation = context.get(
            "escalation",
            "UNKNOWN",
        )

        if agent_action == "REQUEST_CORRECTION":
            explanation = (
                "The port call cannot proceed because "
                "one or more compliance requirements "
                "must be corrected."
            )

        elif agent_action == "REQUEST_INSPECTION":
            explanation = (
                "The port call requires physical "
                "inspection before workflow processing "
                "can continue."
            )

        elif agent_action == "REQUEST_HUMAN_REVIEW":
            explanation = (
                "The port call requires human review "
                "before further action can be taken."
            )

        elif agent_action == "PROCEED":
            explanation = (
                "The current compliance and risk checks "
                "allow the port call workflow to proceed."
            )

        else:
            explanation = (
                "The agent could not determine a supported "
                "workflow action."
            )

        return {
            "provider": "mock",
            "agent_action": agent_action,
            "explanation": explanation,
            "compliance_status": compliance_status,
            "risk_level": risk_level,
            "inspection_decision": inspection_decision,
            "escalation": escalation,
        }