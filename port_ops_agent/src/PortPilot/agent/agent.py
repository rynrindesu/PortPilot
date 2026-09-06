from PortPilot.agent.tools import (
    check_port_call_tool,
    start_inspection_tool,
    complete_inspection_tool,
    advance_port_call_tool,
)

from PortPilot.workflow.state import (
    PortCallState,
    PortCallStatus,
)

from PortPilot.agent.llm import (
    LLMProvider,
    MockLLMProvider,
)

from PortPilot.agent.prompts import (
    PORTPILOT_SYSTEM_PROMPT,
    PORTPILOT_DECISION_PROMPT,
)

def generate_llm_explanation(
    *,
    llm: LLMProvider,
    agent_action: str,
    result: dict,
):
    """
    Generate an explanation of an already-computed
    deterministic PortPilot decision.

    The LLM does not determine the decision.
    """

    compliance = result["compliance"]
    risk = result["risk"]
    inspection = result["inspection"]
    escalation = result["escalation"]
    port_call = result["port_call"]

    context = {
        "agent_action": agent_action,

        "compliance_status": (
            compliance.status
        ),

        "compliance_issues": [
            issue.model_dump()
            for issue in compliance.issues
        ],

        "risk_level": (
            risk["risk_level"]
        ),

        "risk_score": (
            risk["risk_score"]
        ),

        "risk_factors": (
            risk["risk_factors"]
        ),

        "inspection_decision": (
            inspection["decision"]
        ),

        "escalation": (
            escalation["action"]
        ),

        "workflow_phase": (
            port_call.phase.value
        ),

        "workflow_status": (
            port_call.status.value
        ),
    }

    llm_response = llm.invoke(
        system_prompt=PORTPILOT_SYSTEM_PROMPT,
        user_prompt=PORTPILOT_DECISION_PROMPT,
        context=context,
    )

    return llm_response.model_dump()

def run_port_call_agent(
    state: PortCallState,
    llm: LLMProvider | None = None,
):
    """
    Run the local PortPilot agent.

    The agent does not make compliance decisions itself.
    It calls deterministic tools and interprets
    the structured result.
    """
    
    if llm is None:
        llm = MockLLMProvider()

    result = check_port_call_tool(state)

    compliance_status = (
        result["compliance"].status
    )

    risk_level = (
        result["risk"]["risk_level"]
    )

    inspection_decision = (
        result["inspection"]["decision"]
    )

    escalation_action = (
        result["escalation"]["action"]
    )

    if escalation_action == "CORRECTION_REQUIRED":

        agent_action = "REQUEST_CORRECTION"

        llm_result = generate_llm_explanation(
            llm=llm,
            agent_action=agent_action,
            result=result,
        )

        return {
            "agent_action": agent_action,
            "message": (
                "The submitted port-call documents "
                "contain compliance issues that must "
                "be corrected before processing can continue."
            ),
            "llm": llm_result,
            "compliance_status": compliance_status,
            "risk_level": risk_level,
            "inspection_decision": inspection_decision,
            "escalation": escalation_action,
            "result": result,
        }

    if escalation_action == "INSPECTION_REQUIRED":

        agent_action = "REQUEST_INSPECTION"

        llm_result = generate_llm_explanation(
            llm=llm,
            agent_action=agent_action,
            result=result,
        )

        return {
            "agent_action": agent_action,
            "message": (
                "The port call requires a human "
                "physical inspection before it can proceed."
            ),
            "llm": llm_result,
            "compliance_status": compliance_status,
            "risk_level": risk_level,
            "inspection_decision": inspection_decision,
            "escalation": escalation_action,
            "result": result,
        }

    if escalation_action == "HUMAN_REVIEW":

        agent_action = "REQUEST_HUMAN_REVIEW"

        llm_result = generate_llm_explanation(
            llm=llm,
            agent_action=agent_action,
            result=result,
        )

        return {
            "agent_action": agent_action,
            "message": (
                "The port call requires human review "
                "before further workflow action."
            ),
            "llm": llm_result,
            "compliance_status": compliance_status,
            "risk_level": risk_level,
            "inspection_decision": inspection_decision,
            "escalation": escalation_action,
            "result": result,
        }

    agent_action = "PROCEED"

    llm_result = generate_llm_explanation(
        llm=llm,
        agent_action=agent_action,
        result=result,
    )

    return {
        "agent_action": agent_action,

        "message": (
            "The port call passed the current "
            "compliance and risk checks."
        ),

        "llm": llm_result,

        "compliance_status": compliance_status,
        "risk_level": risk_level,
        "inspection_decision": inspection_decision,
        "escalation": escalation_action,

        "result": result,
    }


def agent_start_inspection(
    state: PortCallState,
):
    """
    Agent wrapper for starting an inspection.

    The underlying workflow still enforces whether
    inspection is actually allowed.
    """

    return start_inspection_tool(state)


def agent_complete_inspection(
    state: PortCallState,
    *,
    cleared: bool,
    findings: str | None = None,
):
    """
    Agent wrapper for recording a human
    inspection result.
    """

    return complete_inspection_tool(
        state,
        cleared=cleared,
        findings=findings,
    )


def agent_advance_port_call(
    state: PortCallState,
):
    """
    Agent wrapper for advancing the workflow.

    advance_port_call() remains the safety gate.
    """

    return advance_port_call_tool(state)