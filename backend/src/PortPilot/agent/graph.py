"""LangGraph workflow for PortPilot's rescheduling agent."""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Annotated, Literal, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
)

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from PortPilot.agent.tools import TOOLS

MAX_AGENT_ITERATIONS = 12

# Executes tool calls requested by the model.
tool_node = ToolNode(TOOLS)

AgentOutcome = Literal[
    "rescheduled",
    "pending_review",
    "no_action",
    "unable_to_resolve",
    "failed",
]

 
class AgentState(TypedDict, total=False):
    """Shared state carried through the rescheduling agent graph."""
    # total=False constructs the initial state without all fields present 
    
    # Conversation and tool-call history of agent by appending 
    messages: Annotated[list[AnyMessage], add_messages]

    # ETA change event for this workflow
    vessel_name: str
    imo_number: str
    previous_eta: datetime | None
    new_eta: datetime

    # Used to store the results from tool
    schedule_result: dict
    ranked_result: dict

    # The agent's selected scheduling option
    selected_option_id: str
    selected_option: dict
    decision_reason: str

    # Write and post-write verification
    write_attempted: bool
    write_result: dict
    verification_result: dict

    # Escalation and final result 
    flagged_resources: list[str]
    outcome: AgentOutcome
    errors: list[str]

    # Tracks the number of times the agent has been looping 
    # Want to cap this at a certain number to prevent infinite loop
    iteration_count: int
    replan_count: int


def _normalize_eta(value: datetime | str | None, field_name: str) -> datetime | None:
    """Convert an ETA value to a timezone-aware UTC datetime."""

    if value is None:
        return None

    try:
        if isinstance(value, datetime):
            eta = value
        elif isinstance(value, str):
            eta = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise TypeError(f"expected datetime or ISO-8601 string, got {type(value).__name__}")
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {field_name}: {error}") from error

    if eta.tzinfo is None:
        eta = eta.replace(tzinfo=timezone.utc)

    return eta.astimezone(timezone.utc)


def initial_state(event: Mapping[str, object]) -> AgentState:
    """Validate an ETA-change event and create the graph's initial state."""

    if event.get("event") != "ETA_CHANGED":
        raise ValueError("The agent graph requires an ETA_CHANGED event.")

    vessel_name = str(event.get("vessel_name") or "").strip()
    imo_number = str(event.get("imo_number") or "").strip()

    if not vessel_name:
        raise ValueError("ETA-change event is missing vessel_name.")

    if not imo_number:
        raise ValueError("ETA-change event is missing imo_number.")

    new_eta = _normalize_eta(event.get("new_eta"), "new_eta")
    if new_eta is None:
        raise ValueError("ETA-change event is missing new_eta.")

    previous_eta = _normalize_eta(event.get("previous_eta"), "previous_eta")

    trigger_message = HumanMessage(
        content=(
            f"An ETA change was detected for {vessel_name} "
            f"(IMO {imo_number}). Previous ETA: "
            f"{previous_eta.isoformat() if previous_eta else 'unknown'}. "
            f"New ETA: {new_eta.isoformat()}. "
            "Investigate the operational impact and resolve it using the available tools."
        )
    )

    return AgentState(
        messages=[trigger_message],
        vessel_name=vessel_name,
        imo_number=imo_number,
        previous_eta=previous_eta,
        new_eta=new_eta,
        write_attempted=False,
        flagged_resources=[],
        errors=[],
        iteration_count=0,
        replan_count=0,
    )

# Calls the model to decide what to do next and records its response.
# The response may contain a tool request, which the graph routes to the tool node.
def create_chatbot_node(
    model: BaseChatModel,
    system_prompt: str,
) -> Callable[[AgentState], dict]:
    """Create the graph node that asks the tool-enabled model what to do next."""

    if not system_prompt.strip():
        raise ValueError("A system prompt is required.")

    # Bind once while constructing the graph, rather than on every graph turn.
    model_with_tools = model.bind_tools(TOOLS)

    def chatbot_node(state: AgentState) -> dict:
        """Ask the agent to reason, call a tool, or return a final response."""

        messages = state.get("messages", [])
        iteration_count = state.get("iteration_count", 0) + 1

        response = model_with_tools.invoke(
            [
                SystemMessage(content=system_prompt),
                *messages,
            ]
        )

        return {
            "messages": [response],
            "iteration_count": iteration_count,
        }

    return chatbot_node

# Inspects the decision of the chatbot through history, and decides where the graph should go next
# Conditional edge on the graph
def route_after_chatbot(
    state: AgentState,
) -> Literal["validate_tools", "finalize"]:
    """Route tool requests for validation, or finish when the agent responds."""

    # Prevent the agent from reasoning or calling tools forever.
    if state.get("iteration_count", 0) >= MAX_AGENT_ITERATIONS:
        return "finalize"

    messages = state.get("messages", [])
    if not messages:
        return "finalize"

    last_message = messages[-1]

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "validate_tools"

    return "finalize"