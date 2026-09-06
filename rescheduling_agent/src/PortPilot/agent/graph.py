"""LangGraph workflow for PortPilot's rescheduling agent."""
import json

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Annotated, Literal, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from PortPilot.agent.tools import (
    TOOLS,
    get_vessel_schedule as get_vessel_schedule_tool,
)

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

    # Result of checking the model's latest tool request.
    tool_call_valid: bool

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

    # Most recently executed tool and its parsed result.
    last_tool_name: str
    last_tool_result: dict

    # The result returned to the graph's caller
    final_result: dict

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


# Create a ToolMessage with a rejection call ID so the chatbot sees why the request was rejected
def _reject_tool_call(
    state: AgentState,
    tool_call: dict,
    reason: str,
) -> dict:
    """Reject a tool request and return the reason to the agent."""

    return {
        "messages": [
            ToolMessage(
                content=reason,
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
                status="error",
            )
        ],
        "tool_call_valid": False,
        "errors": [
            *state.get("errors", []),
            reason,
        ],
    }


def _normalize_numbers(value):
    """Recursively convert every int to a float (bools excluded - bool is a
    subclass of int in Python, but True/False are not numbers to normalize).

    A model's tool-calling round trip can collapse a computed score like
    720.0 into the integer 720 - the same value, but json.dumps(720) and
    json.dumps(720.0) are different strings, which broke exact-match
    comparison in _canonical_option for an otherwise-identical option.
    Applying this to both sides before comparing removes that spurious
    difference without changing what "equal" means for anything else.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, dict):
        return {key: _normalize_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_numbers(item) for item in value]
    return value


def _canonical_option(option: dict) -> str:
    """Create a stable representation for comparing scheduling options."""

    return json.dumps(
        _normalize_numbers(option),
        sort_keys=True,
        separators=(",", ":"),
        default=lambda value: (
            value.isoformat()
            if isinstance(value, datetime)
            else str(value)
        ),
    )

    
def validate_tool_call_node(state: AgentState) -> dict:
    """Validate the model's requested tool before allowing execution."""

    messages = state.get("messages", [])
    if not messages:
        return {
            "tool_call_valid": False,
            "errors": [*state.get("errors", []), "No message was available to validate."],
        }

    last_message = messages[-1]

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {
            "tool_call_valid": False,
            "errors": [*state.get("errors", []), "No tool call was available to validate."],
        }

    # Start with one tool call per agent turn. This keeps writes and their
    # results easy to validate, explain, and audit.
    if len(last_message.tool_calls) != 1:
        reason = "The agent must request exactly one tool per turn."

        rejection_messages = [
            ToolMessage(
                content=reason,
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
                status="error",
            )
            for tool_call in last_message.tool_calls
        ]

        return {
            "messages": rejection_messages,
            "tool_call_valid": False,
            "errors": [*state.get("errors", []), reason],
        }

    tool_call = last_message.tool_calls[0]
    tool_name = tool_call["name"]
    arguments = tool_call.get("args", {})

    allowed_tools = {tool.name for tool in TOOLS}

    if tool_name not in allowed_tools:
        return _reject_tool_call(
            state,
            tool_call,
            f"Unknown or unavailable tool: {tool_name}.",
        )

    # Tools that operate on a vessel must use the vessel that triggered
    # this graph run.
    requested_vessel = arguments.get("vessel_name")
    requested_imo = arguments.get("imo_number")

    if requested_vessel is not None and requested_vessel != state["vessel_name"]:
        return _reject_tool_call(
            state,
            tool_call,
            "The requested vessel does not match the ETA-change event.",
        )

    if requested_imo is not None and str(requested_imo) != state["imo_number"]:
        return _reject_tool_call(
            state,
            tool_call,
            "The requested IMO number does not match the ETA-change event.",
        )

    if tool_name == "get_ranked_options":
        try:
            requested_eta = _normalize_eta(
                arguments.get("new_eta"),
                "new_eta",
            )
        except ValueError as error:
            return _reject_tool_call(
                state,
                tool_call,
                str(error),
            )

        if requested_eta != state["new_eta"]:
            return _reject_tool_call(
                state,
                tool_call,
                "get_ranked_options must use the revised ETA from the triggering event.",
            )

    if tool_name == "reschedule_operations":
        ranked_result = state.get("ranked_result")

        if ranked_result is None:
            return _reject_tool_call(
                state,
                tool_call,
                "Ranked options must be retrieved before rescheduling.",
            )

        option_id = arguments.get("option_id")

        if not isinstance(option_id, str) or not option_id.strip():
            return _reject_tool_call(
                state,
                tool_call,
                "reschedule_operations requires an option_id.",
            )

        ranked_options = ranked_result.get("options", [])

        matching_option = next(
            (
                option
                for option in ranked_options
                if option.get("option_id") == option_id
            ),
            None,
        )

        if matching_option is None:
            return _reject_tool_call(
                state,
                tool_call,
                "The submitted option_id does not match an option returned by "
                "get_ranked_options.",
            )

        if matching_option.get("strategy") == "retain_current_allocation":
            return _reject_tool_call(
                state,
                tool_call,
                "retain_current_allocation requires no database write. "
                "Use complete_no_action to finish with a no_action outcome.",
            )

        reason = arguments.get("reason", "")

        if not isinstance(reason, str) or not reason.strip():
            return _reject_tool_call(
                state,
                tool_call,
                "A reason is required when applying a schedule option.",
            )

        return {
            "tool_call_valid": True,
            "selected_option": matching_option,
            "selected_option_id": option_id,
            "decision_reason": reason.strip(),
        }

    if tool_name == "flag_for_review":
        resource_type = arguments.get("resource_type")

        if resource_type not in {"berth", "pilot", "tug"}:
            return _reject_tool_call(
                state,
                tool_call,
                "resource_type must be berth, pilot, or tug.",
            )


    if tool_name == "complete_no_action":
        ranked_result = state.get("ranked_result")

        if ranked_result is None:
            return _reject_tool_call(
                state,
                tool_call,
                "Ranked options must be retrieved before completing with no action.",
            )

        option_id = arguments.get("option_id")

        matching_option = next(
            (
                option
                for option in ranked_result.get("options", [])
                if option.get("option_id") == option_id
                and option.get("strategy") == "retain_current_allocation"
            ),
            None,
        )

        if matching_option is None:
            return _reject_tool_call(
                state,
                tool_call,
                "No valid retain_current_allocation option matches this request.",
            )

        reason = arguments.get("reason", "")

        if not isinstance(reason, str) or not reason.strip():
            return _reject_tool_call(
                state,
                tool_call,
                "A reason is required when completing with no action.",
            )
            
    return {"tool_call_valid": True}


def route_after_tool_validation(
    state: AgentState,
    ) -> Literal["tools", "chatbot"]:
    """Route approved requests to execution and rejected requests to the agent."""

    if state.get("tool_call_valid", False):
        return "tools"

    return "chatbot"


def _find_tool_call_arguments(
    messages: list[AnyMessage],
    tool_call_id: str,
) -> dict:
    """Find the model arguments associated with a ToolMessage."""

    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue

        for tool_call in message.tool_calls:
            if tool_call.get("id") == tool_call_id:
                return tool_call.get("args", {})

    return {}


def process_tool_result_node(state: AgentState) -> dict:
    """Parse the latest ToolMessage and store its result in graph state."""

    messages = state.get("messages", [])

    if not messages or not isinstance(messages[-1], ToolMessage):
        reason = "No tool result was available to process."
        return {
            "errors": [*state.get("errors", []), reason],
        }

    tool_message = messages[-1]
    tool_name = tool_message.name or ""

    try:
        result = json.loads(tool_message.content)
    except (json.JSONDecodeError, TypeError) as error:
        reason = f"{tool_name} returned invalid JSON: {error}"
        return {
            "last_tool_name": tool_name,
            "last_tool_result": {},
            "errors": [*state.get("errors", []), reason],
        }

    if not isinstance(result, dict):
        reason = f"{tool_name} returned a result that was not an object."
        return {
            "last_tool_name": tool_name,
            "last_tool_result": {},
            "errors": [*state.get("errors", []), reason],
        }

    update = {
        "last_tool_name": tool_name,
        "last_tool_result": result,
    }

    if tool_name == "get_vessel_schedule":
        update["schedule_result"] = result

    elif tool_name == "get_ranked_options":
        update["ranked_result"] = result

        retain_option = next(
            (
                option
                for option in result.get("options", [])
                if option.get("strategy") == "retain_current_allocation"
            ),
            None,
        )

        # Deterministic validation for when current allocation is retained
        if retain_option is not None:
            update["outcome"] = "no_action"
            update["selected_option"] = retain_option
            update["selected_option_id"] = retain_option["option_id"]
            update["decision_reason"] = (
                "The existing berth, pilot, and tug allocations remain "
                "feasible for the revised ETA."
            )

    elif tool_name == "reschedule_operations":
        update["write_attempted"] = True
        update["write_result"] = result

        arguments = _find_tool_call_arguments(
            messages,
            tool_message.tool_call_id,
        )
        update["selected_option_id"] = arguments.get("option_id")
        update["decision_reason"] = arguments.get("reason", "")

    elif tool_name == "flag_for_review":
        if result.get("success"):
            resource_type = result.get("resource_type")
            flagged_resources = list(state.get("flagged_resources", []))

            if resource_type and resource_type not in flagged_resources:
                flagged_resources.append(resource_type)

            update["flagged_resources"] = flagged_resources
    elif tool_name == "complete_no_action":
        if result.get("success"):
            update["outcome"] = "no_action"
            update["selected_option_id"] = result.get("option_id")
            update["decision_reason"] = result.get("reason", "")

    return update


def route_after_tool_result(
    state: AgentState,
    ) -> Literal["verify", "chatbot", "finalize"]:
    """Verify successful schedule writes; return all other results to the agent."""

    if state.get("outcome") == "no_action":
        return "finalize"

    if (
        state.get("last_tool_name") == "reschedule_operations"
        and state.get("last_tool_result", {}).get("success") is True
    ):
        return "verify"

    return "chatbot"


# -- Helper function of verify_node to compare 2 datetime
def _same_datetime(left: object, right: object) -> bool:
    """Compare two datetime values after normalizing them to UTC."""

    if left is None or right is None:
        return False

    try:
        return (
            _normalize_eta(left, "verification time")
            == _normalize_eta(right, "verification time")
        )
    except ValueError:
        return False


# -- Checks the correctness of the post-write to the database 
#
# Answers whether the databae contains exactly the allocations of the selected option requested. 
# Only runs after a successful used of 'reschedule_operations' tool. 
def verify_node(state: AgentState) -> dict:

    selected_option = state.get("selected_option")

    if not isinstance(selected_option, dict):
        result = {
            "verified": False,
            "checked_vessels": [],
            "mismatches": ["No selected option was available for verification."],
        }
        return {
            "verification_result": result,
            "messages": [
                HumanMessage(
                    content=f"Post-write verification result: {json.dumps(result)}"
                )
            ],
        }

    mismatches = []
    checked_vessels = []

    # For each of the affected vessels, it checks the changes are consistent with the selected plan. 
    for change in selected_option.get("changes", []):
        vessel_name = change["vessel_name"]
        imo_number = change["imo_number"]

        checked_vessels.append({
            "vessel_name": vessel_name,
            "imo_number": imo_number,
        })

        # Gets the schedule for the affected vessel from the database 
        try:
            raw_schedule = get_vessel_schedule_tool.invoke({
                "vessel_name": vessel_name,
                "imo_number": imo_number,
            })
            schedule = json.loads(raw_schedule)
        except Exception as error:
            mismatches.append(
                f"Could not read the schedule for {vessel_name} "
                f"({imo_number}): {error}"
            )
            continue

        if not schedule.get("found") or not schedule.get("valid"):
            mismatches.append(
                f"No valid schedule was found for {vessel_name} ({imo_number})."
            )
            continue

        actual_allocations = schedule.get("allocations", {})

        # Checks that the expected resources allocations exists
        for resource_type, expected in change.get("allocations", {}).items():
            actual = actual_allocations.get(resource_type)

            if actual is None:
                mismatches.append(
                    f"{vessel_name} has no {resource_type} allocation."
                )
                continue

            if actual.get("resource_id") != expected.get("resource_id"):
                mismatches.append(
                    f"{vessel_name}'s {resource_type} resource does not match: "
                    f"expected {expected.get('resource_id')}, "
                    f"found {actual.get('resource_id')}."
                )

            if not _same_datetime(
                actual.get("start_time"),
                expected.get("start_time"),
            ):
                mismatches.append(
                    f"{vessel_name}'s {resource_type} start time does not match."
                )

            if not _same_datetime(
                actual.get("end_time"),
                expected.get("end_time"),
            ):
                mismatches.append(
                    f"{vessel_name}'s {resource_type} end time does not match."
                )

            if actual.get("buffer_minutes") != expected.get("buffer_minutes"):
                mismatches.append(
                    f"{vessel_name}'s {resource_type} buffer does not match."
                )

            # Ensure the resource allocations are also confirmed.
            if actual.get("status") != "confirmed":
                mismatches.append(
                    f"{vessel_name}'s {resource_type} allocation status does not match: "
                    f"expected confirmed, found {actual.get('status')}."
                )

    # Tabulates the number of mismatches and returns to the agent
    result = {
        "verified": len(mismatches) == 0,
        "checked_vessels": checked_vessels,
        "mismatches": mismatches,
    }

    return {
        "verification_result": result,
        # The model must see the verification result before giving its answer.
        "messages": [
            HumanMessage(
                content=(
                    "Deterministic post-write verification result: "
                    f"{json.dumps(result)}"
                )
            )
        ],
    }


def _last_agent_response(state: AgentState) -> str:
    """Return the model's most recent ordinary response."""

    for message in reversed(state.get("messages", [])):
        if (
            isinstance(message, AIMessage)
            and not message.tool_calls
            and isinstance(message.content, str)
        ):
            return message.content

    return ""


def _determine_outcome(state: AgentState) -> AgentOutcome:
    """Determine the workflow outcome from objective graph state."""

    verification = state.get("verification_result")

    if verification is not None:
        if verification.get("verified") is True:
            return "rescheduled"
        return "failed"

    if state.get("flagged_resources"):
        return "pending_review"

    write_result = state.get("write_result")

    if state.get("write_attempted") and (
        not isinstance(write_result, dict)
        or write_result.get("success") is not True
    ):
        return "unable_to_resolve"

    schedule_result = state.get("schedule_result")

    if schedule_result is not None and (
        not schedule_result.get("found")
        or not schedule_result.get("valid")
    ):
        return "failed"

    if state.get("outcome") == "no_action":
        return "no_action"

    if state.get("iteration_count", 0) >= MAX_AGENT_ITERATIONS:
        return "unable_to_resolve"

    # The model stopped without applying, verifying, or escalating.
    return state.get("outcome", "unable_to_resolve")


def finalize_node(state: AgentState) -> dict:
    """Build the stable result returned by the completed graph."""

    outcome = _determine_outcome(state)

    if outcome == "no_action":
        vessel_name = state.get("vessel_name") or "The vessel"
        agent_response = (
            f"{vessel_name}: no action required. The existing berth, pilot, "
            "and tug allocations remain feasible for the revised ETA. "
            "No schedule changes were applied."
        )
    else:
        agent_response = _last_agent_response(state)

    if not agent_response:
        if outcome == "rescheduled":
            agent_response = "The schedule was updated and verified."
        elif outcome == "pending_review":
            agent_response = "The unresolved allocations were flagged for human review."
        elif outcome == "failed":
            agent_response = "The scheduling workflow failed."
        else:
            agent_response = "The agent could not complete the scheduling workflow."

    # The model's own prose is not a reliable record of what was actually
    # escalated - it can (and has) claimed a resource was flagged for review
    # without ever making that tool call. For the two outcomes where that
    # matters, append the real, state-derived list so a mismatch between the
    # narrative and reality is always visible rather than silently trusted.
    if outcome in ("pending_review", "unable_to_resolve"):
        flagged_resources = state.get("flagged_resources", [])
        agent_response = (
            f"{agent_response} "
            f"[System record: resource type(s) actually flagged for review "
            f"this run: {flagged_resources if flagged_resources else 'none'}.]"
        )

    final_result = {
        "outcome": outcome,
        "vessel_name": state.get("vessel_name"),
        "imo_number": state.get("imo_number"),
        "previous_eta": (
            state["previous_eta"].isoformat()
            if state.get("previous_eta")
            else None
        ),
        "new_eta": (
            state["new_eta"].isoformat()
            if state.get("new_eta")
            else None
        ),
        "selected_option_id": state.get("selected_option_id"),
        "flagged_resources": state.get("flagged_resources", []),
        "write_result": state.get("write_result"),
        "verification_result": state.get("verification_result"),
        "agent_response": agent_response,
        "errors": state.get("errors", []),
        "iterations": state.get("iteration_count", 0),
    }

    return {
        "outcome": outcome,
        "final_result": final_result,
    }
