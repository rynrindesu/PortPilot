"""Orchestrates PortPilot's rescheduling agent: builds the LLM-driven
LangGraph for ETA changes, and runs the deterministic retry path for new
vessels with an unconfirmed resource.
"""

import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# Select the LLM provider from the environment, defaulting to Groq.
# Set LLM_PROVIDER=bedrock to use Amazon Bedrock instead.
PROVIDER = os.environ.get("LLM_PROVIDER", "groq")

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
BEDROCK_MODEL = os.environ.get(
    "BEDROCK_MODEL", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
)
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get(
    "AWS_REGION", "ap-southeast-1"
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
3. When calling reschedule_operations, pass the complete option object
   exactly as returned by get_ranked_options - no field added, removed, or
   changed - together with a non-empty reason explaining your choice.

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

RETRY POLICY
If reschedule_operations fails because the option is no longer valid, call
get_ranked_options once more to get options reflecting the current database
state, then choose again. If the second reschedule attempt also fails, stop retrying and use
flag_for_review for each affected resource type that requires escalation.

This is different from a write that succeeds but then fails verification.
If reschedule_operations reports success and the deterministic verification
that follows finds a mismatch, do not attempt another schedule change. A
write already happened; retrying now would layer an uncertain second change
on top of a state you do not understand yet. Report that the update could
not be verified instead - do not call flag_for_review for this either, since
that tool is for escalating a resource with no valid option, not a write
whose outcome is uncertain.

COMPLETION CONDITIONS
Your job is done as soon as one of the following happens:
- reschedule_operations succeeds and the deterministic verification that
  follows confirms it - base your final answer on what verification
  actually reports, not on what you expect it to say. If verification
  instead finds a mismatch, do not claim the schedule was updated; report
  that the update could not be verified (see RETRY POLICY).
- The current allocation already satisfies the revised ETA - call
  complete_no_action with that retain_current_allocation option's option_id
  and a reason, rather than making an unnecessary change.
- No valid option exists after your one retry - call flag_for_review for
  each affected resource_type, citing the specific reason get_ranked_options
  gave you.

Once you reach one of these, give a plain final answer summarizing what
happened and why. Do not call any more tools after that.
"""
