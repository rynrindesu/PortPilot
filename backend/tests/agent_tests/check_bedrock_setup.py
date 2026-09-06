"""Verify AWS Bedrock is reachable through PortPilot.agent.agent.create_model()
before wiring it into the full LangGraph agent.

Usage from the repository root:
    PYTHONPATH=backend/src python backend/tests/agent_tests/check_bedrock_setup.py

Checks, in order:
  1. LLM_PROVIDER is set to "bedrock".
  2. boto3 can resolve AWS credentials at all (profile, static keys, or role)
     and they identify a real caller - catches expired temporary/session
     tokens before wasting a Bedrock call on them.
  3. create_model() can produce a plain text completion.
  4. The model can bind a tool and actually call it - the agent graph
     depends on this, not just plain text completions.
"""

import sys

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from PortPilot.agent.agent import AWS_REGION, BEDROCK_MODEL, PROVIDER, create_model


@tool
def ping(message: str) -> str:
    """Echo back the given message. Used only to test tool-calling."""
    return f"pong: {message}"


def main() -> int:
    print(f"provider: {PROVIDER}")
    print(f"model:    {BEDROCK_MODEL}")
    print(f"region:   {AWS_REGION}")

    if PROVIDER != "bedrock":
        print(
            f"\nLLM_PROVIDER is {PROVIDER!r}, not 'bedrock' - this script tests "
            "the Bedrock path specifically. Run with LLM_PROVIDER=bedrock."
        )
        return 1

    print("\nresolving AWS credentials...")
    try:
        import boto3

        session = boto3.Session()
        creds = session.get_credentials()
        if creds is None:
            raise RuntimeError(
                "No credentials found via AWS_PROFILE, static keys, or an "
                "instance/task role."
            )
        identity = session.client("sts", region_name=AWS_REGION).get_caller_identity()
        print(f"  caller: {identity['Arn']}")
    except ImportError as error:
        print(f"\nFAILED: {error}\n  Run: pip install boto3")
        return 1
    except Exception as error:
        print(f"\nFAILED: {type(error).__name__}: {error}")
        message = str(error).lower()
        if "expired" in message or "token" in message:
            print(
                "  Temporary credentials look expired. Refresh them - either "
                "re-paste new AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/"
                "AWS_SESSION_TOKEN, or `aws sso login --profile <name>`."
            )
        return 1

    print("\ncreating model via create_model()...")
    try:
        model = create_model()
    except ImportError as error:
        print(f"\nFAILED: {error}\n  Run: pip install langchain-aws")
        return 1

    print("invoking a plain text completion...")
    try:
        response = model.invoke([HumanMessage(content="Reply with exactly: ready")])
    except Exception as error:
        print(f"\nFAILED: {type(error).__name__}: {error}")
        message = str(error).lower()
        if "accessdenied" in message.replace(" ", ""):
            print(
                f"  Credentials are valid but model access isn't granted for "
                f"{BEDROCK_MODEL!r} in {AWS_REGION!r}. Check AWS console -> "
                "Bedrock -> Model access, in that exact region."
            )
        elif "validationexception" in message.replace(" ", ""):
            print(
                f"  {BEDROCK_MODEL!r} isn't available in {AWS_REGION!r} for this "
                "account. Check the console for the correct model id, then:\n"
                "    export BEDROCK_MODEL=<id from the console>"
            )
        elif "throttl" in message:
            print("  Rate limited - wait a moment and re-run.")
        return 1
    print(f"  model said: {response.content.strip()!r}")

    print("\nbinding a tool and checking the model can call it...")
    model_with_tools = model.bind_tools([ping])
    tool_response = model_with_tools.invoke(
        [HumanMessage(content="Call the ping tool with the message 'hello'.")]
    )
    if not tool_response.tool_calls:
        print(
            "\nFAILED: the model responded without calling the tool.\n"
            f"  Raw response: {tool_response.content!r}\n"
            "  Tool-calling is required for the real agent graph to work - "
            f"if this keeps happening, {BEDROCK_MODEL} may not support it reliably."
        )
        return 1
    call = tool_response.tool_calls[0]
    print(f"  tool call: {call['name']}({call['args']})")

    print("\nOK - Bedrock is ready for the agent graph.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
