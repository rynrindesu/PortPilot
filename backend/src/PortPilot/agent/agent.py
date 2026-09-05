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
