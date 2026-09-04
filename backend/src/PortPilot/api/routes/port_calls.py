from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from PortPilot.workflow.state import (
    PortCallPhase,
    PortCallState,
    PortCallStatus,
)

from PortPilot.workflow.orchestrator import (
    process_port_call,
    advance_port_call,
)

from PortPilot.models.documents import (
    ExtractedDocument,
)


router = APIRouter(
    prefix="/port-calls",
    tags=["Port Calls"],
)


# --------------------------------------------------
# Temporary in-memory storage
# --------------------------------------------------

PORT_CALLS: dict[str, PortCallState] = {}


# --------------------------------------------------
# Request models
# --------------------------------------------------

class CreatePortCallRequest(BaseModel):
    port_call_id: str

    vessel_name: str | None = None
    imo_number: str | None = None
    call_sign: str | None = None

    first_singapore_call: bool = False

    purpose_of_call: str | None = None

    carrying_dangerous_goods: bool = False
    radioactive_material: bool = False


# --------------------------------------------------
# Create Port Call
# --------------------------------------------------

@router.post("")
def create_port_call(
    request: CreatePortCallRequest,
):
    if request.port_call_id in PORT_CALLS:
        raise HTTPException(
            status_code=409,
            detail="Port call already exists.",
        )

    state = PortCallState(
        port_call_id=request.port_call_id,

        vessel_name=request.vessel_name,
        imo_number=request.imo_number,
        call_sign=request.call_sign,

        phase=PortCallPhase.ARRIVAL,
        status=PortCallStatus.ARRIVAL_PENDING,

        first_singapore_call=(
            request.first_singapore_call
        ),

        purpose_of_call=request.purpose_of_call,

        carrying_dangerous_goods=(
            request.carrying_dangerous_goods
        ),

        radioactive_material=(
            request.radioactive_material
        ),
    )

    PORT_CALLS[
        request.port_call_id
    ] = state

    return state


# --------------------------------------------------
# Get Port Call
# --------------------------------------------------

@router.get("/{port_call_id}")
def get_port_call(
    port_call_id: str,
):
    state = PORT_CALLS.get(port_call_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Port call not found.",
        )

    return state


# --------------------------------------------------
# Submit Documents
# --------------------------------------------------

@router.post("/{port_call_id}/documents")
def submit_documents(
    port_call_id: str,
    documents: list[ExtractedDocument],
):
    state = PORT_CALLS.get(port_call_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Port call not found.",
        )

    state.documents = documents

    return {
        "success": True,
        "port_call_id": port_call_id,
        "document_count": len(documents),
        "documents": documents,
    }


# --------------------------------------------------
# Run Compliance Check
# --------------------------------------------------

@router.post("/{port_call_id}/check")
def check_port_call(
    port_call_id: str,
):
    state = PORT_CALLS.get(port_call_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Port call not found.",
        )

    result = process_port_call(
        state,
        state.documents,
    )

    return result


# --------------------------------------------------
# Advance Port Call
# --------------------------------------------------

@router.post("/{port_call_id}/advance")
def advance(
    port_call_id: str,
):
    state = PORT_CALLS.get(port_call_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Port call not found.",
        )

    result = advance_port_call(state)

    return {
        "port_call_id": port_call_id,
        "result": result,
        "state": state,
    }