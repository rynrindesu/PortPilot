# import re

# from PortPilot.models.documents import (
#     ExtractedDocument,
#     ExtractedField,
# )


# def find_value(pattern: str, text: str):
#     match = re.search(
#         pattern,
#         text,
#         re.IGNORECASE,
#     )

#     if match:
#         return match.group(1).strip()

#     return None


# def extract_document(
#     text: str,
#     document_type: str,
# ) -> ExtractedDocument:

#     vessel_name = find_value(
#         r"vessel\s+name\s*[:\-]\s*(.+)",
#         text,
#     )

#     imo_number = find_value(
#         r"imo\s+(?:number|no\.?)\s*[:\-]\s*(\d+)",
#         text,
#     )

#     call_sign = find_value(
#         r"call\s+sign\s*[:\-]\s*(.+)",
#         text,
#     )

#     gross_tonnage = find_value(
#         r"gross\s+tonnage\s*[:\-]\s*([\d,]+(?:\.\d+)?)",
#         text,
#     )

#     flag = find_value(
#         r"(?:flag|flag state)\s*[:\-]\s*(.+)",
#         text,
#     )

#     return ExtractedDocument(
#         document_type=document_type,

#         vessel_name=(
#             ExtractedField(
#                 value=vessel_name,
#                 confidence=0.90,
#                 source_text=vessel_name,
#             )
#             if vessel_name
#             else None
#         ),

#         imo_number=(
#             ExtractedField(
#                 value=imo_number,
#                 confidence=0.95,
#                 source_text=imo_number,
#             )
#             if imo_number
#             else None
#         ),

#         call_sign=(
#             ExtractedField(
#                 value=call_sign,
#                 confidence=0.90,
#                 source_text=call_sign,
#             )
#             if call_sign
#             else None
#         ),

#         gross_tonnage=(
#             ExtractedField(
#                 value=float(gross_tonnage.replace(",", "")),
#                 confidence=0.95,
#                 source_text=gross_tonnage,
#             )
#             if gross_tonnage
#             else None
#         ),

#         flag=(
#             ExtractedField(
#                 value=flag,
#                 confidence=0.90,
#                 source_text=flag,
#             )
#             if flag
#             else None
#         ),
#     )

import json
import os
import re

from openai import OpenAI

from PortPilot.compliance.fields import REQUIRED_FIELDS
from PortPilot.models.documents import (
    ExtractedDocument,
    ExtractedField,
)


MODEL = os.getenv("PORTPILOT_EXTRACTION_MODEL", "gpt-5.6-luna")

# Every field the schema can hold, derived from the model rather than written
# out by hand. The compliance engine rejects a document for any required field
# the extractor never asked for, so a hand-maintained list here quietly turns
# into CORRECTION_REQUIRED on perfectly valid paperwork.
EXTRACTABLE_FIELDS = [
    name for name in ExtractedDocument.model_fields if name != "document_type"
]

_client = None


def _get_client() -> OpenAI:
    """Build the OpenAI client on first use.

    Constructing it at import time makes the whole service unimportable
    without OPENAI_API_KEY: uvicorn refuses to boot and pytest cannot even
    collect. Deferring it means only the code paths that actually call the
    model need a key.
    """
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def _build_prompt(text: str, document_type: str) -> str:
    required = set(REQUIRED_FIELDS.get(document_type, []))

    field_lines = []
    for name in EXTRACTABLE_FIELDS:
        suffix = "  (required for this document type)" if name in required else ""
        field_lines.append(f"- {name}{suffix}")
    field_list = "\n".join(field_lines)

    return f"""
You are a maritime document information extraction system.

Document type:
{document_type}

Extract information ONLY when it is explicitly present in the document.
Do NOT guess or infer missing information. If a field is not present in the
document, return null for it.

Return a single JSON object. Each key is one of the field names listed below,
and each value is either null or an object with:

- value
- confidence, a number between 0 and 1
- source_text, the exact text from the document the value came from

Fields to extract:

{field_list}

Return only the JSON object, with no surrounding prose and no code fences.

DOCUMENT:

{text}
"""


def _parse(raw_output: str) -> dict:
    """Read the model's JSON, tolerating code fences and stray prose."""
    cleaned = (raw_output or "").strip()

    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fall back to the outermost JSON object in the response.
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _coerce(raw) -> ExtractedField | None:
    """Normalise one field into an ExtractedField, or drop it entirely."""
    if raw is None:
        return None

    if isinstance(raw, dict):
        if raw.get("value") is None:
            return None
        try:
            confidence = float(raw.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        return ExtractedField(
            value=raw.get("value"),
            confidence=min(1.0, max(0.0, confidence)),
            source_text=raw.get("source_text"),
        )

    # Some responses return a bare scalar rather than the wrapper object.
    # Score it mid-confidence: the value is usable but unattributed.
    return ExtractedField(value=raw, confidence=0.5, source_text=str(raw))


def extract_document(
    text: str,
    document_type: str,
) -> ExtractedDocument:

    response = _get_client().responses.create(
        model=MODEL,
        input=_build_prompt(text, document_type),
    )

    data = _parse(response.output_text)

    fields = {}
    for name in EXTRACTABLE_FIELDS:
        field = _coerce(data.get(name))
        if field is not None:
            fields[name] = field

    return ExtractedDocument(document_type=document_type, **fields)
