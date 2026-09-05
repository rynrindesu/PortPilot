"""Verify Groq is reachable through PortPilot.agent.agent.create_model()
before wiring it into the full LangGraph agent.

Usage from the repository root:
    PYTHONPATH=backend/src python backend/tests/check_groq_setup.py

Checks, in order:
  1. GROQ_API_KEY is set.
  2. create_model() can produce a plain text completion.
  3. The model can bind a tool and actually call it - the agent graph
     depends on this, not just plain text completions.
"""

import os
import sys

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from PortPilot.agent.agent import GROQ_MODEL, PROVIDER, create_model


@tool
def ping(message: str) -> str:
    """Echo back the given message. Used only to test tool-calling."""
    return f"pong: {message}"


def main() -> int:
    print(f"provider: {PROVIDER}")
    print(f"model:    {GROQ_MODEL}")

    if PROVIDER != "groq":
        print(
            f"\nLLM_PROVIDER is {PROVIDER!r}, not 'groq' - this script tests the "
            "Groq path specifically. Run with LLM_PROVIDER=groq (or unset it, "
            "since 'groq' is the default)."
        )
        return 1

    if not os.environ.get("GROQ_API_KEY"):
        print(
            "\nNo GROQ_API_KEY found.\n"
            "  1. Sign in at https://console.groq.com (free, no card)\n"
            "  2. API Keys -> Create API Key -> copy it now (shown once)\n"
            "  3. export GROQ_API_KEY=gsk_...\n"
            "     or add GROQ_API_KEY=gsk_... to a .env file"
        )
        return 1

    print("\ncreating model via create_model()...")
    try:
        model = create_model()
    except ImportError as error:
        print(f"\nFAILED: {error}\n  Run: pip install langchain-groq")
        return 1

    print("invoking a plain text completion...")
    try:
        response = model.invoke([HumanMessage(content="Reply with exactly: ready")])
    except Exception as error:
        print(f"\nFAILED: {type(error).__name__}: {error}")
        message = str(error).lower()
        if "authentication" in message or "401" in message:
            print("  The key was rejected - copy it again from console.groq.com.")
        elif "rate" in message or "429" in message:
            print("  Rate limited on the free tier - wait a minute and re-run.")
        elif "model" in message:
            print(
                f"  Groq did not recognise {GROQ_MODEL!r}. Check "
                "https://console.groq.com/docs/models and then:\n"
                "    export GROQ_MODEL=<id from that page>"
            )
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
            f"if this keeps happening, {GROQ_MODEL} may not support it reliably."
        )
        return 1
    call = tool_response.tool_calls[0]
    print(f"  tool call: {call['name']}({call['args']})")

    print("\nOK - Groq is ready for the agent graph.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
