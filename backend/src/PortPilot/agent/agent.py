"""Orchestrates PortPilot's rescheduling agent: builds the LLM-driven
LangGraph for ETA changes, and runs the deterministic retry path for new
vessels with an unconfirmed resource.
"""

import logging
import os

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

from PortPilot.agent.graph import (
    AgentState,
    create_chatbot_node,
    finalize_node,
    initial_state,
    process_tool_result_node,
    route_after_chatbot,
    route_after_tool_result,
    route_after_tool_validation,
    tool_node,
    validate_tool_call_node,
    verify_node,
)
from PortPilot.monitoring.monitor_service import (
    monitor_vessels,
    retry_unconfirmed_operations,
)
from PortPilot.database.postgres import get_unconfirmed_vessel_keys

logger = logging.getLogger(__name__)

load_dotenv()

# Select the LLM provider from the environment, defaulting to Groq.
# Set LLM_PROVIDER=bedrock to use Amazon Bedrock instead.
PROVIDER = os.environ.get("LLM_PROVIDER", "groq")

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

BEDROCK_MODEL = os.environ.get(
    "BEDROCK_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
)
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get(
    "AWS_REGION", "us-east-1"
)


def _bedrock_runtime():
    """Create a Bedrock Runtime client with extended request timeouts.
    """
    import boto3
    from botocore.config import Config

    return boto3.client(
        "bedrock-runtime",
        config=Config(
            region_name=AWS_REGION,
            read_timeout=300,
            connect_timeout=120,
            retries={"max_attempts": 1},
        ),
    )


def create_model(temperature: float = 0.0):
    """A LangChain chat model for whichever provider PROVIDER names.

    Both ChatGroq and ChatBedrockConverse implement the same BaseChatModel
    interface, so build_graph() doesn't need to know which one it's holding.
    boto3/langchain-aws are only imported on the Bedrock path, so a
    Groq-only setup never needs them installed.
    """
    if PROVIDER == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=GROQ_MODEL, temperature=temperature)

    if PROVIDER == "bedrock":
        from langchain_aws import ChatBedrockConverse

        return ChatBedrockConverse(
            model_id=BEDROCK_MODEL,
            client=_bedrock_runtime(),
            temperature=temperature,
        )

    raise ValueError(f"Unknown LLM_PROVIDER {PROVIDER!r}. Use 'groq' or 'bedrock'.")


SYSTEM_PROMPT = """You are PortPilot's rescheduling agent for the Port of Singapore.

You are given one vessel whose ETA has changed. Your job is to resolve any
resulting scheduling conflict for that vessel using only the tools provided.

SEQUENCE
1. Call get_vessel_schedule to see the vessel's current allocations before
   doing anything else.
2. Call get_ranked_options with the revised ETA to get deterministically
   generated, validated, and ranked scheduling options. Never invent a berth,
   pilot, tug, resource ID, or time yourself - only use values that appear in
   a returned option.
3. When calling reschedule_operations, pass only the option_id exactly as
   returned by get_ranked_options, together with a non-empty reason explaining
   your choice. The application retrieves the complete option from graph state.

PRIORITIES
Options are already ranked best-to-worst by a fixed, deterministic order
(fewest vessels affected, smallest schedule shift, fewest repeat disruptions,
best resource utilisation). Normally select the highest-ranked valid option.
If you choose a lower-ranked option instead, give a clear reason grounded in
the actual scheduling trade-offs - not just a restatement of the rank.

PROHIBITED
- Request exactly one tool call per turn - never more than one at once.
- Never modify a vessel's identity (vessel_name, imo_number) or its ETA.
- Never call a tool for any vessel other than the one you were given.
- Do not call the same tool with identical arguments more than twice during
  one graph run. Repeated calls should only be made when the scheduling state
  may have changed.

STRICT TOOL-CALLING FORMAT
When calling reschedule_operations, issue exactly one native tool call.
The arguments must be a valid JSON object in this form:
{"option_id": "<option_id>", "reason": "<reason>"}
Do not copy the option's vessels, resources, allocations, or timestamps into
the tool call.

RETRY POLICY
If reschedule_operations fails because the selected option is no longer valid,
call get_ranked_options exactly once more to refresh the options against the
current database state, then choose again. If the second reschedule attempt
also fails, stop retrying and call flag_for_review once for each affected
resource_type that requires escalation.

If get_ranked_options returns no valid options at all, including on the first
call, there is nothing to submit to reschedule_operations and therefore
nothing to retry. Do not call get_ranked_options again. Call flag_for_review
once for each affected resource_type, using the specific invalid reason(s)
returned by get_ranked_options.

A successful write followed by failed verification is a different case.
If reschedule_operations reports success but deterministic verification finds
a mismatch, do not attempt another reschedule and do not call flag_for_review.
A write has already occurred, so report that the update could not be verified
and stop.

COMPLETION CONDITIONS

Your job is complete as soon as one of the following occurs:

- reschedule_operations succeeds and deterministic verification confirms the
  applied schedule. Base the final answer only on the verified result.
- The current allocation already satisfies the revised ETA. Call
  complete_no_action using the retain_current_allocation option_id and provide
  a reason. Do not call reschedule_operations for this option.
- No valid scheduling option exists, either immediately or after the single
  permitted retry. Call flag_for_review once for every affected resource_type
  before giving the final answer, citing the relevant invalid reason.

Never claim that a resource was rescheduled, retained, verified, or escalated
unless the corresponding tool result or deterministic state confirms it.

Once you reach one of these, give the final answer immediately. Do
not call any more tools.

FINAL ANSWER FORMAT
Write 2 to 4 concise sentences in plain prose. Do not use markdown tables,
headers, or bullet lists.

State:
- the vessel name and outcome;
- which scheduling strategy was used (retain_current_allocation,
  shift_same_resources, alternative_resources, or reallocate_one_vessel),
  if an option was selected;
- for a successful reschedule, only the resources that changed and the
  reason for the change;
- for no action, that the existing schedule was retained and why;
- for escalation or failure, what could not be resolved and what happens
  next;
- whether verification succeeded, if a schedule change was applied.

Do not include unchanged resource details, option rankings, option IDs,
tool calls, iteration counts, or other internal workflow details.
"""


def build_graph(model, system_prompt):
    """Assemble and compile the rescheduling agent's LangGraph state machine.

    model is any LangChain BaseChatModel; system_prompt is passed straight to
    create_chatbot_node(), which requires a non-empty string.
    """
    graph_builder = StateGraph(AgentState)

    # Register every node, including the shared ToolNode(TOOLS) instance
    # created in graph.py for executing validated tool calls.
    graph_builder.add_node("chatbot", create_chatbot_node(model, system_prompt))
    graph_builder.add_node("validate_tools", validate_tool_call_node)
    graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("process_tool_result", process_tool_result_node)
    graph_builder.add_node("verify", verify_node)
    graph_builder.add_node("finalize", finalize_node)

    graph_builder.set_entry_point("chatbot")

    # The model either requests a tool or gives a final answer.
    graph_builder.add_conditional_edges(
        "chatbot",
        route_after_chatbot,
        {"validate_tools": "validate_tools", "finalize": "finalize"},
    )

    # An approved tool call executes; a rejected one goes back to the model
    # with the rejection reason already in its message history.
    graph_builder.add_conditional_edges(
        "validate_tools",
        route_after_tool_validation,
        {"tools": "tools", "chatbot": "chatbot"},
    )

    graph_builder.add_edge("tools", "process_tool_result")

    # A successful write is verified against the database; every other tool
    # result goes back to the model to decide what to do next.
    graph_builder.add_conditional_edges(
        "process_tool_result",
        route_after_tool_result,
        {"verify": "verify", "chatbot": "chatbot", "finalize": "finalize"},
    )

    # Return verification to the model so its final response is based on the
    # actual database result rather than the expected write outcome.
    graph_builder.add_edge("verify", "chatbot")
    graph_builder.add_edge("finalize", END)

    return graph_builder.compile()


# Build the graph only when first needed, then cache it for reuse.
# This avoids initialization during import and rebuilding it for each vessel.
_COMPILED_GRAPH = None

def _get_compiled_graph():
    """Return the cached compiled agent graph, building it on first use."""
    global _COMPILED_GRAPH
    
    if _COMPILED_GRAPH is None:
        logger.info("Building the agent graph (provider=%s)", PROVIDER)
        _COMPILED_GRAPH = build_graph(create_model(), SYSTEM_PROMPT)
    return _COMPILED_GRAPH


def _process_eta_change(event: dict) -> dict:
    """Convert one ETA_CHANGED event into graph state, 
    run the agent, and return the final result.
    """
    vessel_name = event["vessel_name"]
    imo_number = event["imo_number"]

    logger.info("Processing ETA_CHANGED for %s (%s)", vessel_name, imo_number)

    state = initial_state(event)
    result_state = _get_compiled_graph().invoke(state)
    final_result = result_state["final_result"]

    logger.info(
        "%s (%s) -> outcome=%s",
        vessel_name, imo_number, final_result.get("outcome"),
    )
    return final_result


def _retry_unconfirmed_vessel(event: dict) -> dict:
    """Retry one vessel's unconfirmed allocations using deterministic scheduling.
    """
    vessel_name = event["vessel_name"]
    imo_number = event["imo_number"]

    logger.info("Retrying unconfirmed vessel %s (%s)", vessel_name, imo_number)

    result = retry_unconfirmed_operations(vessel_name, imo_number)

    logger.info(
        "%s (%s) -> outcome=%s",
        vessel_name, imo_number, result.get("outcome"),
    )
    return result


def _deduplicate_events(events: list) -> list:
    """Collapse duplicate vessel events within one poll batch.

    OCEANS-X may return the same vessel multiple times with different ETAs.
    Since monitor_vessels() processes and persists rows sequentially, the
    later event is kept so it matches the final state stored in the database.

    Identical duplicates are silently ignored. Conflicting duplicates are
    logged as warnings before the later event replaces the earlier one.
    """
    by_key = {}
    order = []
    for event in events:
        key = (event["vessel_name"], event["imo_number"])
        if key not in by_key:
            by_key[key] = event
            order.append(key)
            continue

        previous_event = by_key[key]
        if previous_event == event:
            continue

        logger.warning(
            "Conflicting duplicate events for %s (%s) in this poll - keeping "
            "the later one since it matches what monitor_vessels() persisted "
            "last. earlier=%s later=%s",
            event["vessel_name"], event["imo_number"], previous_event, event,
        )
        by_key[key] = event

    return [by_key[key] for key in order]


def run_monitoring_cycle(date, not_before=None, current_vessels=None) -> dict:
    """Poll OCEANS-X and process all resulting scheduling events.

    ETA changes are processed first through the agent graph. Once they are
    complete, newly discovered vessels with unconfirmed allocations are
    retried using deterministic scheduling.

    Each vessel is processed independently so one failure does not stop
    the rest of the monitoring cycle.
    """
    changes = _deduplicate_events(
        monitor_vessels(
            date,
            not_before=not_before,
            current_vessels=current_vessels,
        )
    )

    eta_change_events = [event for event in changes if event["event"] == "ETA_CHANGED"]
    unconfirmed_events = [
        event for event in changes
        if event["event"] == "NEW_VESSEL_DISCOVERED"
        and any(info["status"] == "unconfirmed" for info in event["assigned"].values())
    ]
    queued_unconfirmed = {
        (event["vessel_name"], event["imo_number"])
        for event in unconfirmed_events
    }
    for vessel in get_unconfirmed_vessel_keys():
        key = (vessel["vessel_name"], vessel["imo_number"])
        if key not in queued_unconfirmed:
            unconfirmed_events.append(vessel)
            queued_unconfirmed.add(key)

    errors = []

    eta_change_results = []
    for event in eta_change_events:
        try:
            eta_change_results.append(_process_eta_change(event))
        except Exception as error:
            logger.exception(
                "Failed to process ETA_CHANGED for %s (%s)",
                event["vessel_name"], event["imo_number"],
            )
            errors.append({
                "vessel_name": event["vessel_name"],
                "imo_number": event["imo_number"],
                "phase": "eta_change",
                "error": str(error),
            })

    unconfirmed_retry_results = []
    for event in unconfirmed_events:
        try:
            unconfirmed_retry_results.append(_retry_unconfirmed_vessel(event))
        except Exception as error:
            logger.exception(
                "Failed to retry unconfirmed vessel %s (%s)",
                event["vessel_name"], event["imo_number"],
            )
            errors.append({
                "vessel_name": event["vessel_name"],
                "imo_number": event["imo_number"],
                "phase": "unconfirmed_retry",
                "error": str(error),
            })

    return {
        "eta_change_results": eta_change_results,
        "unconfirmed_retry_results": unconfirmed_retry_results,
        "raw_changes": changes,
        "errors": errors,
    }
