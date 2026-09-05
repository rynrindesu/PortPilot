from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from PortPilot.agent.graph import (
    run_agent_graph,
    run_inspection_start,
    run_inspection_completion,
)

from PortPilot.agent.agent import (
    agent_advance_port_call,
)

from PortPilot.api.routes.port_calls import (
    PORT_CALLS,
)


router = APIRouter(
    prefix="/agent",
    tags=["Agent"],
)


class InspectionCompletionRequest(BaseModel):
    cleared: bool
    findings: str | None = None


@router.post("/port-calls/{port_call_id}/run")
def run_port_call_agent_endpoint(
    port_call_id: str,
):
    state = PORT_CALLS.get(port_call_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Port call not found.",
        )

    result = run_agent_graph(state)

    return {
        "port_call_id": port_call_id,
        "result": result,
    }


@router.post(
    "/port-calls/{port_call_id}/inspection/start"
)
def agent_start_inspection_endpoint(
    port_call_id: str,
):
    state = PORT_CALLS.get(port_call_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Port call not found.",
        )

    result = run_inspection_start(state)

    if (
        result["graph_status"]
        == "INSPECTION_START_BLOCKED"
    ):
        raise HTTPException(
            status_code=400,
            detail=result["inspection"]["message"],
        )

    return {
        "port_call_id": port_call_id,
        "result": result,
    }


@router.post(
    "/port-calls/{port_call_id}/inspection/complete"
)
def agent_complete_inspection_endpoint(
    port_call_id: str,
    request: InspectionCompletionRequest,
):
    state = PORT_CALLS.get(port_call_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Port call not found.",
        )

    result = run_inspection_completion(
        state,
        cleared=request.cleared,
        findings=request.findings,
    )

    if (
        result["graph_status"]
        == "INSPECTION_COMPLETION_BLOCKED"
    ):
        raise HTTPException(
            status_code=400,
            detail=result["inspection"]["message"],
        )

    return {
        "port_call_id": port_call_id,
        "result": result,
    }


@router.post(
    "/port-calls/{port_call_id}/advance"
)
def agent_advance_port_call_endpoint(
    port_call_id: str,
):
    state = PORT_CALLS.get(port_call_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Port call not found.",
        )

    result = agent_advance_port_call(state)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result["message"],
        )

    return {
        "port_call_id": port_call_id,
        "result": result,
        "state": state,
    }