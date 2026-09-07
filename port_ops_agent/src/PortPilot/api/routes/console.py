"""Read-only endpoints for the operations console.

Additive: the compliance engine, the workflow and the agent are untouched.
This router only projects the port calls the service already holds into the
shape the console renders.
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from PortPilot.api.routes.port_calls import PORT_CALLS
from PortPilot.compliance.engine import run_compliance_check
from PortPilot.compliance.escalation import determine_escalation
from PortPilot.compliance.inspection import determine_inspection_decision
from PortPilot.compliance.port_call import PortCall
from PortPilot.compliance.risk import calculate_risk_score


router = APIRouter(tags=["Console"])


def _document_payload(port_call_id: str, index: int, document) -> dict:
    """Flatten an ExtractedDocument into id + typed fields for the console."""

    raw = document.model_dump() if hasattr(document, "model_dump") else dict(document)
    document_type = raw.get("document_type") or "unknown"

    fields = {}
    for name, value in raw.items():
        if name == "document_type" or value is None:
            continue
        if isinstance(value, dict) and "value" in value:
            fields[name] = {
                "value": value.get("value"),
                "confidence": float(value.get("confidence") or 0.0),
                "source_text": value.get("source_text"),
            }

    return {
        "document_id": f"{port_call_id}-DOC-{index:02d}",
        "document_type": document_type,
        "file_name": f"{document_type}.pdf",
        "pages": 1,
        "extraction_method": (
            "textract_ocr"
            if any(f["confidence"] and f["confidence"] < 0.75 for f in fields.values())
            else "text_layer"
        ),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
    }


def _project(state) -> dict:
    """Run the real engines over a stored port call and shape the result."""

    port_call = PortCall(
        vessel_name=state.vessel_name,
        imo_number=state.imo_number,
        call_sign=state.call_sign,
        phase=state.phase.value,
        first_singapore_call=state.first_singapore_call,
        purpose_of_call=state.purpose_of_call,
        carrying_dangerous_goods=state.carrying_dangerous_goods,
        radioactive_material=state.radioactive_material,
    )

    compliance = run_compliance_check(port_call, state.documents)
    inconsistent = any(i.code == "FIELD_MISMATCH" for i in compliance.issues)

    risk = calculate_risk_score(
        port_call,
        compliance_status=compliance.status,
        document_inconsistency=inconsistent,
    )
    inspection = determine_inspection_decision(
        port_call,
        risk_level=risk["risk_level"],
        compliance_status=compliance.status,
    )
    escalation = determine_escalation(
        compliance_status=compliance.status,
        physical_inspection_required=inspection["decision"] == "inspection_required",
    )

    agent_action = (
        "REQUEST_CORRECTION"
        if compliance.status == "CORRECTION_REQUIRED"
        else "REQUEST_HUMAN_REVIEW"
        if compliance.status == "HUMAN_REVIEW"
        else "REQUEST_INSPECTION"
        if inspection["decision"] == "inspection_required"
        else "PROCEED"
    )

    return {
        "port_call_id": state.port_call_id,
        "vessel_name": state.vessel_name or "",
        "imo_number": state.imo_number or "",
        "call_sign": state.call_sign or "",
        "flag": "",
        "phase": state.phase.value,
        "status": state.status.value,
        "first_singapore_call": state.first_singapore_call,
        "purpose_of_call": state.purpose_of_call or "",
        "carrying_dangerous_goods": state.carrying_dangerous_goods,
        "radioactive_material": state.radioactive_material,
        "berth": "",
        "eta": "",
        "documents": [
            _document_payload(state.port_call_id, i + 1, d)
            for i, d in enumerate(state.documents)
        ],
        "events": [
            {
                "event": e.event,
                "description": e.description,
                "source": e.source,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            for e in reversed(state.events)
        ],
        "compliance": {
            "status": compliance.status,
            "issues": [i.model_dump() for i in compliance.issues],
        },
        "risk": risk,
        "inspection": inspection,
        "escalation": escalation,
        "agent_action": agent_action,
        "agent_reasoning": "",
    }


@router.get("/port-calls")
def list_port_calls():
    """Every port call currently held by the service."""

    return [_project(state) for state in PORT_CALLS.values()]
