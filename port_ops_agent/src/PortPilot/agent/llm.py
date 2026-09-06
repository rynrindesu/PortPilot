from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict


class LLMResponse(BaseModel):
    """
    Safe output boundary for PortPilot LLM providers.

    LLMs may provide explanatory content only.
    They cannot return authoritative workflow fields.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    provider: str
    explanation: str


class LLMProvider(ABC):
    """
    Provider-neutral interface for PortPilot LLMs.
    """

    @abstractmethod
    def invoke(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: dict[str, Any] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """
    Local deterministic mock LLM.
    """

    def invoke(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        context: dict[str, Any] | None = None,
    ) -> LLMResponse:

        context = context or {}

        agent_action = context.get(
            "agent_action",
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

        return LLMResponse(
            provider="mock",
            explanation=explanation,
        )